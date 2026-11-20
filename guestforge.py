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
        qemu, "-machine", "virt,accel=hvf,pflash0=uefi,pflash1=nvram",
        "-cpu", "host", "-smp", str(options.cpus), "-m", f"{options.memory}G",
        "-display", "cocoa", "-serial", "none", "-monitor", "none",
        "-device", "ramfb", "-device", "qemu-xhci,id=usb",
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
            binary, "socket", "--tpm2", "--tpmstate", f"dir={directory}",
            "--ctrl", f"type=unixio,path={socket}",
        ])
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


def create_vm(vm, size, image_tool, vars_file):
    vm.parent.mkdir(parents=True, exist_ok=True)
    vm.mkdir(mode=0o700)
    try:
        shutil.copyfile(vars_file, vm / "uefi-vars.fd")
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
    for name in ("iso", "drivers"):
        path = getattr(options, name)
        if path is not None:
            setattr(options, name, readable_file(path))
    with (vm / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"This VM is already running: {vm}") from None
        with running_tpm(tpm, vm / "tpm") as socket:
            subprocess.run(qemu_command(qemu, vm, options, code, socket), check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Check the host and required tools")
    create = commands.add_parser("create", help="Create persistent VM storage")
    create.add_argument("vm", type=Path)
    create.add_argument("--disk-size", type=int, default=256, metavar="GIB")
    create.add_argument("--vars-template", type=Path)
    start = commands.add_parser("start", help="Launch an existing VM")
    start.add_argument("vm", type=Path)
    start.add_argument("--iso", type=Path, help="Attach Windows 11 ARM64 installation media")
    start.add_argument("--drivers", type=Path, help="Attach a VirtIO drivers ISO")
    start.add_argument("--firmware", type=Path, help="Override the AArch64 UEFI firmware")
    start.add_argument("--memory", type=int, default=8, metavar="GIB")
    start.add_argument("--cpus", type=int, default=4)
    options = parser.parse_args()

    try:
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise ValueError("GuestForge requires native ARM64 Python on Apple silicon macOS.")
        if options.command == "doctor":
            missing = False
            for name in ("qemu-system-aarch64", "qemu-img", "swtpm"):
                path = shutil.which(name)
                print(f"{name}: {path or 'missing'}")
                missing |= path is None
                if name == "qemu-system-aarch64" and path:
                    for file in firmware(path):
                        present = file.is_file()
                        print(f"{file}: {'found' if present else 'missing'}")
                        missing |= not present
            return int(missing)
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
