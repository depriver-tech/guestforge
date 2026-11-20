#!/usr/bin/env python3
"""Create and launch a Windows ARM64 virtual machine on Apple silicon."""

import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time


def executable(name):
    path = shutil.which(name)
    if path is None:
        raise ValueError(f"{name} was not found on PATH.")
    return path


def firmware(qemu):
    prefix = Path(qemu).resolve().parent.parent
    return (
        prefix / "share/qemu/edk2-aarch64-code.fd",
        prefix / "share/qemu/edk2-arm-vars.fd",
    )


ARM_VIRT_FLASH_SIZE = 64 * 1024**2


QEMU_CAPABILITIES = (
    ("HVF acceleration", ("-accel", "help"), "hvf"),
    ("TPM emulator backend", ("-tpmdev", "help"), "emulator"),
    ("ARM TPM device", ("-device", "help"), '"tpm-tis-device"'),
)


def probe(binary, arguments, expected=None):
    try:
        result = subprocess.run(
            [binary, *arguments], capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    output = f"{result.stdout}\n{result.stderr}".strip()
    if expected is None:
        if result.returncode == 0:
            return None
    elif any(expected == token.rstrip(",") for token in output.split()):
        # Some QEMU help commands exit nonzero after listing supported options.
        return None
    return output or f"exit status {result.returncode}"


def doctor(vnc=False):
    console = (("VNC display", ("-help",), "-vnc") if vnc
               else ("Cocoa display", ("-display", "help"), "cocoa"))
    checks = {}
    for name in ("qemu-system-aarch64", "qemu-img", "swtpm"):
        path = shutil.which(name)
        arguments = ("socket", "--print-capabilities") if name == "swtpm" else ("--version",)
        error = probe(path, arguments) if path else "missing from PATH"
        checks[name] = error
        print(f"{name}: {path if error is None else error}")
        if name != "qemu-system-aarch64" or error is not None:
            continue
        for file in firmware(path):
            present = file.is_file() and os.access(file, os.R_OK)
            checks[str(file)] = None if present else "missing or unreadable"
            print(f"{file}: {'readable' if present else checks[str(file)]}")
        for label, arguments, expected in (*QEMU_CAPABILITIES, console):
            error = probe(path, arguments, expected)
            checks[label] = error
            print(f"{label}: {'available' if error is None else 'unavailable'}")
    return int(any(error is not None for error in checks.values()))


def readable_file(path):
    path = path.expanduser().resolve(strict=True)
    if not path.is_file() or not os.access(path, os.R_OK):
        raise ValueError(f"Expected a readable file: {path}")
    return path


def drive(path, identifier, fmt, read_only=False):
    return ["-blockdev", json.dumps({
        "driver": fmt,
        "node-name": identifier,
        "read-only": read_only,
        "file": {"driver": "file", "filename": str(path)},
    })]


def qemu_command(qemu, vm, options, code, socket):
    command = [
        qemu, "-machine", "virt,accel=hvf,gic-version=3,pflash0=uefi,pflash1=nvram",
        "-cpu", "host", "-smp", str(options.cpus), "-m", f"{options.memory}G",
        "-display", "none" if options.vnc else "cocoa",
        "-serial", "none", "-monitor", "none",
        "-device", options.display_device, "-device", "qemu-xhci,id=usb",
        "-device", "usb-kbd,bus=usb.0", "-device", "usb-tablet,bus=usb.0",
        "-netdev", "user,id=internet", "-device", "virtio-net-pci,netdev=internet",
        "-chardev", f"socket,id=tpmsock,path={socket}",
        "-tpmdev", "emulator,id=tpm0,chardev=tpmsock",
        "-device", "tpm-tis-device,tpmdev=tpm0",
        *drive(code, "uefi", "raw", read_only=True),
        *drive(vm / "uefi-vars.fd", "nvram", "raw"),
        *drive(vm / "windows.qcow2", "windows", "qcow2"),
        "-device", "nvme,drive=windows,serial=guestforge-system,bootindex=2",
    ]
    if options.vnc:
        # QEMU's option string uses a doubled comma for a literal comma.
        vnc_path = str(vm / "vnc.sock").replace(",", ",,")
        command.extend(["-vnc", f"unix:{vnc_path}"])
    for identifier, path in (("installer", options.iso), ("drivers", options.drivers)):
        if path is None:
            continue
        device = f"scsi-cd,bus={identifier}-usb.0,drive={identifier}"
        if identifier == "installer":
            device += ",bootindex=1"
        command.extend([
            *drive(path, identifier, "raw", read_only=True),
            "-device", f"usb-bot,bus=usb.0,id={identifier}-usb",
            "-device", device,
        ])
    return command


@contextlib.contextmanager
def running_tpm(binary, directory):
    with tempfile.TemporaryDirectory(prefix="gf-", dir="/tmp") as temporary:
        socket = Path(temporary) / "tpm.sock"
        process = subprocess.Popen([
            binary, "socket", "--tpm2", "--tpmstate", "dir=.",
            "--ctrl", f"type=unixio,path={socket}",
        ], cwd=directory)
        try:
            deadline = time.monotonic() + 5
            while not socket.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise ValueError("swtpm failed to start.")
                time.sleep(0.05)
            yield socket
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def prepare_uefi_vars(path):
    # QEMU's ARM virt board maps the variables file as a 64 MiB flash bank.
    # Some EDK II builds ship only the populated prefix as their template.
    with path.open("r+b") as stream:
        size = os.fstat(stream.fileno()).st_size
        if not 0 < size <= ARM_VIRT_FLASH_SIZE:
            raise ValueError(f"Invalid ARM UEFI variables file size ({size} bytes): {path}")
        if size < ARM_VIRT_FLASH_SIZE:
            stream.truncate(ARM_VIRT_FLASH_SIZE)


def create_vm(vm, size, image_tool, vars_file):
    vm.parent.mkdir(parents=True, exist_ok=True)
    vm.mkdir(mode=0o700)
    try:
        vars_path = vm / "uefi-vars.fd"
        shutil.copyfile(vars_file, vars_path)
        prepare_uefi_vars(vars_path)
        (vm / "tpm").mkdir(mode=0o700)
        subprocess.run([
            image_tool, "create", "-f", "qcow2", str(vm / "windows.qcow2"), f"{size}G",
        ], check=True)
    except BaseException:
        shutil.rmtree(vm)
        raise


def launch(vm, options, qemu, tpm):
    if not vm.is_dir() or any(
        not (vm / name).is_file() for name in ("windows.qcow2", "uefi-vars.fd")
    ) or not (vm / "tpm").is_dir():
        raise ValueError(f"Create a GuestForge VM at {vm} first.")
    default_code, _ = firmware(qemu)
    code = readable_file(options.firmware or default_code)
    if options.vnc and len(os.fsencode(vm / "vnc.sock")) >= 104:
        raise ValueError("The VM path is too long for a macOS Unix VNC socket.")
    for name in ("iso", "drivers"):
        path = getattr(options, name)
        if path is not None:
            setattr(options, name, readable_file(path))
    with (vm / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"This VM is already running: {vm}") from None
        prepare_uefi_vars(vm / "uefi-vars.fd")
        with running_tpm(tpm, vm / "tpm") as socket:
            subprocess.run(qemu_command(qemu, vm, options, code, socket), check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="Check the host and required tools")
    check.add_argument("--vnc", action="store_true", help="Check for socket-based VNC instead of Cocoa")
    create = commands.add_parser("create", help="Create persistent VM storage")
    create.add_argument("vm", type=Path)
    create.add_argument("--disk-size", type=int, default=256, metavar="GIB")
    create.add_argument("--vars-template", type=Path)
    start = commands.add_parser("start", help="Launch an existing VM")
    start.add_argument("vm", type=Path)
    start.add_argument("--iso", type=Path, help="Attach Windows 11 ARM64 installation media")
    start.add_argument("--drivers", type=Path, help="Attach a VirtIO drivers ISO")
    start.add_argument("--firmware", type=Path, help="Override the AArch64 UEFI firmware")
    start.add_argument("--display-device", choices=("ramfb", "virtio-ramfb"), default="ramfb",
                       help="Select the framebuffer exposed to Windows")
    start.add_argument("--vnc", action="store_true",
                       help="Use a Unix VNC socket in the VM directory instead of Cocoa")
    start.add_argument("--memory", type=int, default=8, metavar="GIB")
    start.add_argument("--cpus", type=int, default=4)
    options = parser.parse_args()

    try:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise ValueError("GuestForge requires native ARM64 Python on Apple silicon macOS.")
        if options.command == "doctor":
            return doctor(options.vnc)
        qemu = executable("qemu-system-aarch64")
        vm = options.vm.expanduser().resolve()
        if options.command == "create":
            if options.disk_size < 64:
                parser.error("--disk-size must be at least 64 GiB")
            _, default_vars = firmware(qemu)
            create_vm(vm, options.disk_size, executable("qemu-img"),
                      readable_file(options.vars_template or default_vars))
        else:
            if options.memory < 4 or options.cpus < 2:
                parser.error("Windows requires at least 4 GiB of RAM and 2 CPUs")
            launch(vm, options, qemu, executable("swtpm"))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"GuestForge: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
