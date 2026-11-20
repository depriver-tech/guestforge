import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import guestforge


class RuntimeChecks(unittest.TestCase):
    def test_capability_help_can_return_nonzero_and_print_to_stderr(self):
        help_result = subprocess.CompletedProcess([], 1, "", "Supported accelerators:\nhvf\ntcg")
        with patch("guestforge.subprocess.run", return_value=help_result):
            self.assertIsNone(guestforge.probe("qemu", ("-accel", "help"), "hvf"))
            self.assertIsNotNone(guestforge.probe("qemu", ("-accel", "help"), "kvm"))

    def test_device_help_accepts_qemu_quoted_names_with_a_trailing_comma(self):
        help_result = subprocess.CompletedProcess([], 0, 'name "tpm-tis-device", bus System', "")
        with patch("guestforge.subprocess.run", return_value=help_result):
            self.assertIsNone(guestforge.probe("qemu", ("-device", "help"), '"tpm-tis-device"'))

    def test_doctor_rejects_qemu_without_tpm_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "bin" / "qemu-system-aarch64"
            for file in guestforge.firmware(binary):
                file.parent.mkdir(parents=True, exist_ok=True)
                file.touch()
            lookup = {
                "qemu-system-aarch64": str(binary),
                "qemu-img": str(root / "bin" / "qemu-img"),
                "swtpm": str(root / "bin" / "swtpm"),
            }

            def probe(binary, arguments, expected=None):
                return "TPM backend unavailable" if expected == "emulator" else None

            with patch("guestforge.shutil.which", side_effect=lookup.get):
                with patch("guestforge.probe", side_effect=probe):
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        self.assertEqual(guestforge.doctor(), 1)
            self.assertIn("TPM emulator backend: unavailable", output.getvalue())

    def test_doctor_accepts_a_complete_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary = root / "bin" / "qemu-system-aarch64"
            for file in guestforge.firmware(binary):
                file.parent.mkdir(parents=True, exist_ok=True)
                file.touch()
            with patch("guestforge.shutil.which", return_value=str(binary)):
                with patch("guestforge.probe", return_value=None):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(guestforge.doctor(), 0)


class LaunchConfiguration(unittest.TestCase):
    def test_vnc_console_stays_on_a_local_socket(self):
        vm = Path("/tmp/Windows, ARM")
        options = SimpleNamespace(
            cpus=4, memory=8, iso=None, drivers=None, vnc=True, display_device="virtio-ramfb",
        )
        command = guestforge.qemu_command("qemu", vm, options, Path("/tmp/code.fd"), Path("/tmp/tpm"))
        self.assertEqual(command[command.index("-display") + 1], "none")
        self.assertEqual(command[command.index("-vnc") + 1], "unix:/tmp/Windows,, ARM/vnc.sock")
        self.assertIn("virtio-ramfb", command)


class FirmwareVariables(unittest.TestCase):
    def test_compact_template_grows_without_changing_its_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "vars.fd"
            data = b"signed EDK II variables"
            file.write_bytes(data)
            guestforge.prepare_uefi_vars(file)
            guestforge.prepare_uefi_vars(file)
            self.assertEqual(file.stat().st_size, guestforge.ARM_VIRT_FLASH_SIZE)
            with file.open("rb") as stream:
                self.assertEqual(stream.read(len(data) + 1), data + b"\0")

    def test_empty_template_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            file = Path(temporary) / "vars.fd"
            file.touch()
            with self.assertRaisesRegex(ValueError, "Invalid ARM UEFI variables"):
                guestforge.prepare_uefi_vars(file)


if __name__ == "__main__":
    unittest.main()
