# GuestForge

GuestForge is an open-source project to run a full Windows desktop on Apple silicon for development and PC gaming.

The first prototype uses QEMU with Apple's Hypervisor framework. It creates persistent virtual disks, UEFI variables and TPM state, then launches a VM with a basic display, USB keyboard and tablet, an NVMe disk and a VirtIO network adapter.

## Start the prototype

Requires Apple silicon macOS, native Python 3, QEMU with Cocoa and HVF, ARM64 EDK II firmware, and swtpm. With Homebrew installed, install the runtime with `brew install qemu swtpm`.

Download the [Windows 11 ARM64 ISO](https://www.microsoft.com/en-us/software-download/windows11arm64) from Microsoft. Obtain a [VirtIO drivers ISO](https://github.com/virtio-win/virtio-win-pkg-scripts/blob/master/README.md) that contains a signed Windows ARM64 NetKVM driver before attempting online setup. Keep VM images and installers outside the tracked source tree.

```sh
python3 guestforge.py doctor
python3 guestforge.py create vms/windows
python3 guestforge.py start vms/windows --iso "/path/to/Windows-arm64.iso" --drivers "/path/to/virtio-win.iso"
```

The `doctor` command checks for the QEMU binaries, readable firmware, HVF acceleration, the selected display backend, and the TPM backend and device compiled into QEMU. Run the launcher's unit tests with `python3 -m unittest discover -s tests -v`.

After installation, shut down from inside Windows, then start without installation media using `python3 guestforge.py start vms/windows`. The VM directory contains the disk, UEFI variables and TPM state. Back up the whole directory with the VM shut down.

Defaults are 4 vCPUs, 8 GiB of RAM and a sparse 256 GiB disk. See `create --help` and `start --help` to change these or supply custom firmware and a matching UEFI variables template.

For a QEMU build that provides `virtio-ramfb` and VNC, use `doctor --vnc` and pass
`--display-device virtio-ramfb --vnc` to `start`. The latter creates
`vnc.sock` in the VM directory. Use a compatible local client to view it.
GuestForge does not open a TCP port for this console.

## Verification status

On an M5 Pro, Windows 11 ARM64 Setup detected the virtual NVMe drive, copied
Windows 11 Home to it, and restarted into Windows Boot Manager on that drive.
This test used QEMU 10.0.12 from UTM 5.0.9-2, UTM's EDK II firmware, a software
TPM and the VirtIO framebuffer. The Windows desktop, installed networking, and
Steam and game compatibility still need separate checks. GuestForge currently
uses a framebuffer for display.

See the [developer and gaming milestones](docs/roadmap.md) for Steam and game compatibility targets. GuestForge source is MIT-licensed. Windows, Steam, QEMU, firmware and guest drivers are installed separately under their respective terms.
