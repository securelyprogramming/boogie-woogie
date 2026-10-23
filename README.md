# Boogie Woogie 🎮

**Bring another controller. The game stays with the host.**

Boogie Woogie is a shared LAN co-op system for Rommayo and Emulatormayo, with its own Android app and browser guest. The Android host runs a game and sends its picture and sound over WebRTC. Approved guests send controller inputs back to their assigned virtual controller.

This source extraction is a development preview. The earlier prototype worked between Android, a browser, and the native Steam Deck app; the new standalone packaging must pass its own device tests before a release is advertised.

| Play your way | Current scope |
| --- | --- |
| Share a single-player adventure | Multiple approved guests share Player 1 |
| Couch co-op over the LAN | Host Player 1 and one dedicated remote Player 2 |
| Watch a friend play | Spectators receive video/audio without an input grant |
| Android host | Local NES import; Rommayo integration uses its existing native RomM session |
| Android / browser guest | Touch controls, saved layouts, quality preferences, FPS display, controller mapping |
| Native Steam Deck guest | Qt Quick + SDL3 receiver uses the same signaling and controller protocol |

The broker only handles admission and WebRTC signaling. Games, saves, RomM cookies, controller packets, video and audio do not pass through it. The host remains responsible for gameplay and saves. Three- and four-player assignments, Bluetooth transport, Chromecast, internet relay and native desktop hosting are future work.

## Start a LAN room

Requirements: Python 3.10+, OpenSSL, and a trusted local network. From this checkout, run one command with **the computer's LAN IPv4**:

```sh
./setup.sh --bind 192.168.1.50
```

The example IP is a placeholder. Without `--bind`, setup listens only on `127.0.0.1`, useful for local development but unreachable by a phone or Deck. An explicit RFC1918 or loopback address is required; setup does not bind every interface or change your firewall.

Setup generates a two-day certificate with the selected IP in its SAN, starts an HTTPS room on port 9443, and writes pairing files to a fresh private directory under `~/.local/share/boogie-woogie/`. It prints the URL and directory path, never the pairing secrets. Stop with **Ctrl+C**. Every start creates a new room; existing files are never overwritten.

1. In Boogie Woogie on Android, choose **Pairing / Connection setup → Import pairing file** and select `host.json` on the host device.
2. Choose **Import NES game**, select a local game file you are authorized to use, then start multiplayer. An embedded Rommayo host can use the main app's existing account instead.
3. Give trusted guests **only `guest.json`**, using a private transfer. Import it on another Android device, or use its invitation in the browser guest at the HTTPS URL. Native Deck guests use the same URL, certificate fingerprint and invitation fields.
4. A guest chooses **Shared Player 1**, **Player 2**, or **Watch only**. The host explicitly approves each join. A compatible two-player game must be running for independent Player 2 gameplay.

The browser needs a certificate it trusts or an explicitly accepted local certificate warning. Setup does not install a CA or suppress browser security warnings. Native clients validate the supplied certificate fingerprint; obtain pairing files through a trusted channel. Invitations expire after ten minutes. Restarting multiplayer on the active host refreshes admission; stopping the broker ends the room.

`host.json` and `session.json` contain host authorization. Keep them on the host/operator's devices, outside this checkout, and out of screenshots or public messages. Guest pairing contains an invitation and should also be kept private. Room credentials are temporary; the broker stores no account database. You can use `--port 9444` for a second room or `--data-dir /absolute/private/directory` for a different data location; that directory must be owned by you, mode 0700 and outside the checkout.

## Controls and presentation

- Hide touch buttons while using a physical controller; **Show controls** stays reachable.
- Edit touch layout and keep it for this game or all games.
- Use the controller mapper's guided capture, multiple input bindings, and directional remapping. Available scopes depend on the client: session, game, and device/model defaults.
- View the current game and host-approved player slot. Local button mapping never grants ownership of another player's slot.
- Adjust video quality and optionally show FPS. Network conditions still affect latency and smoothness.
- Choose game artwork, app artwork or no backdrop, with adjustable dimming. Gameplay is never obscured by the margins.

See [setup and troubleshooting](docs/setup.md), [protocol and security boundaries](docs/protocol.md), [browser controls](web/README.md), and [validation status](docs/validation.md).

## Build and contribute

Android sources live in `android/`; the shared library is reused by the main apps. Runtime assets remain pinned to their existing EmulatorJS version. This project changes app options and session integration; it does not add new emulator-core capabilities. See [Android build and integration](android/README.md) and [native Steam Deck/desktop guest setup](docs/native-guest.md) for reproducible source builds.

Run source checks without starting a room:

```sh
python3 -m unittest discover -s broker -p 'test*.py'
node --test test-*.cjs web/test-*.cjs
```

The workflow calls the organization's pinned centralized security baseline, including secret, dependency, configuration and Actions scans, plus CodeQL. Local tests do not establish a clean remote scan or a new hardware release; those results are tracked separately.

No ROMs, firmware or copyrighted game screenshots are included. Boogie Woogie is a companion tool; obtaining and running games is your responsibility. App-owned source is MIT licensed. Third-party runtimes and emulator cores retain their own licenses and attribution requirements.
