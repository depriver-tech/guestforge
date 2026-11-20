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

The `doctor` command checks for the QEMU binaries, readable firmware, HVF acceleration, Cocoa display, and the TPM backend and device compiled into QEMU. Run the launcher's unit tests with `python3 -m unittest discover -s tests -v`.

After installation, shut down from inside Windows, then start without installation media using `python3 guestforge.py start vms/windows`. The VM directory contains the disk, UEFI variables and TPM state. Back up the whole directory with the VM shut down.

Defaults are 4 vCPUs, 8 GiB of RAM and a sparse 256 GiB disk. See `create --help` and `start --help` to change these or supply custom firmware and a matching UEFI variables template.

## Verification status

GuestForge has a VM launcher. The Windows installer, Secure Boot configuration, signed guest networking driver, desktop boot and reboot persistence still require an end-to-end test on a configured Mac. The display uses a framebuffer. The project has no accelerated Windows graphics driver.

See the [developer and gaming milestones](docs/roadmap.md) for Steam and game compatibility targets. GuestForge source is MIT-licensed. Windows, Steam, QEMU, firmware and guest drivers are installed separately under their respective terms.
