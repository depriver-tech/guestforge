import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import guestforge


class RuntimeChecks(unittest.TestCase):
    def test_capability_help_can_return_nonzero_and_print_to_stderr(self):
        help_result = subprocess.CompletedProcess([], 1, "", "Supported accelerators:\nhvf\ntcg")
        with patch("guestforge.subprocess.run", return_value=help_result):
            self.assertIsNone(guestforge.probe("qemu", ("-accel", "help"), "hvf"))
            self.assertIsNotNone(guestforge.probe("qemu", ("-accel", "help"), "kvm"))

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


if __name__ == "__main__":
    unittest.main()
