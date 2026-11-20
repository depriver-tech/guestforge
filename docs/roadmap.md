# Developer and gaming milestones

## Windows desktop

1. Start the ARM64 installer on Apple silicon. Validate the NVMe disk, TPM 2.0 and Secure Boot with supported firmware and enrolled keys.
2. Install the signed ARM64 network driver, complete Windows setup and verify network access.
3. Shut down and restart without installation media. Confirm changed settings and a saved file persist.
4. Install an ARM64 developer toolchain, compile and debug a sample Windows app, and verify file transfer between the host and guest.

## Steam and gaming

1. In the running Windows desktop, get the [Windows Steam installer](https://store.steampowered.com/about/) from Valve. Use Steam's normal sign-in and library installation flow. Verify that the client opens, signs in and installs a game. Record the Windows, Steam and GuestForge versions and any errors.
2. Add accelerated graphics by defining the Windows virtual GPU interface and a Metal-backed host renderer. Use a Direct3D 12 sample to verify device creation, shader execution and presentation before testing retail games.
3. Verify sound and controller input in the guest. For each game, record launch, menus, gameplay, frame pacing and online compatibility independently.

| Steam title | First gameplay check | Status |
| --- | --- | --- |
| [Forza Horizon 5](https://store.steampowered.com/app/1551360/Forza_Horizon_5/) | Drive a complete race with a controller | Pending Direct3D 12 |
| [Forza Horizon 6](https://store.steampowered.com/app/2483190/Forza_Horizon_6/) | Drive a complete race with a controller | Pending Direct3D 12 |
| [NBA 2K27](https://store.steampowered.com/app/4356430/NBA_2K27/) | Play a complete exhibition game and verify AVX2 compatibility | Pending Direct3D 12 |
| [EA SPORTS FC 27](https://store.steampowered.com/app/4080220/EA_SPORTS_FC_27/) | Launch from Steam through the EA app, pass EA Javelin Anticheat checks, and complete a Kick Off match with a controller | Pending Direct3D 12 and guest compatibility verification |

Verify publisher-supported launch and multiplayer behavior with each game's normal client and anti-cheat. Steam client compatibility, game rendering and online play are separate checks.
