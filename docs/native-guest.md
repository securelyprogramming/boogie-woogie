# Native Steam Deck and desktop guest

`native-guest/` is a standalone SDL3 / aiortc guest for Boogie Woogie protocol 1.
The Android host runs the game; this client receives video/audio and sends only
host-approved controller snapshots. It does not need a ROM, emulator core, or
RomM login. The native main-app Qt library is a separate frontend.

## Install from source

Use Python 3.12 on Linux x86_64. In the repository:

```sh
cd native-guest
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-linux-x86_64.lock
```

The lock pins the tested Linux CPython 3.12 wheels, including all media and Qt
image-decoder dependencies. It pins aiohttp **3.14.4**, the patched release
identified by [the upstream advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-2g87-pp6c-29x5); its wheel hash comes from the
[official PyPI release](https://pypi.org/project/aiohttp/3.14.4/). The complete
Linux lock was installed into a fresh isolated target with hash enforcement,
and all 31 guest tests plus the SDL self-test passed using this version. Other platforms need their own validated wheel lock;
`requirements.txt` records the pinned direct dependencies for development. The
Linux lock must not be used as a Windows/macOS lock.

Install a full SDL3 shared runtime through your platform's package manager or
build the unchanged official SDL **3.2.28** source with the supplied helper:

```sh
bash build-sdl3.sh
```

That helper requires Git, CMake, a C/C++ build toolchain and your Linux display,
audio and input development libraries. It builds into `native-guest/.sdl3/`, uses
no sudo, and pins official commit `7f3ae3d57459e59943a4ecfefc8f6277ec6bf540`.
Existing source changes cause it to stop. The client first checks an explicitly
selected library, its local build, standard Homebrew locations, then the system
loader. Minimum supported SDL API is 3.2.0. For another installation:

```sh
.venv/bin/python boogie_guest.py --sdl-library /absolute/path/to/libSDL3.so.0 --self-test
```

macOS developers can use Homebrew's SDL3; a notarized macOS app and Windows
installer are not provided or validated here. No C++ input shim is needed: this
client calls SDL3 directly through Python's `ctypes`.

## Pair and join

Start [the LAN broker](setup.md) and privately transfer its **guest.json** to the
Deck. Use the guest file, which contains only the HTTPS origin, certificate pin,
invitation and optional quality. Never use the host config. Keep it outside the
repository and readable only by its owner:

```sh
chmod 600 "$HOME/guest.json"
.venv/bin/python boogie_guest.py --config "$HOME/guest.json" --name 'Steam Deck' --role player2 --fullscreen
```

Use your actual file location. No pairing path, host address or credential is
hardcoded. Configuration requires a private LAN IP and pinned HTTPS certificate;
loopback, unspecified/public addresses, hostnames, redirects, paths and URL
credentials are rejected. POSIX ownership/0600 checks are required by this
version; Windows filesystem/packaging support remains pending.

The host must approve every new join. Roles are `player2` for the second emulated
controller, `player` for shared Player 1, and `spectator` for watching without
input authority. Players 3/4, native hosting, Internet relay and Bluetooth
transport are not implemented.

Optional frontend flags:

```sh
.venv/bin/python boogie_guest.py --config "$HOME/guest.json" --role player2 --quality balanced --volume 70 --show-fps --fullscreen
```

`--quality smooth|balanced|sharp` overrides the pairing's video profile at join.
`--volume 0-100` and `--mute` affect only this device's audio. `--show-fps` shows
incoming video frame rate, which differs from the host emulator's frame rate.
These are startup choices; the browser/Android players have their own settings.
`--app-brand rommayo|emulatormayo` chooses the original fallback art; the default
is the green Emulatormayo art. Background mode and dimming remain editable in
Options. No emulator core or save format changes are involved.

For Steam Gaming Mode, add a launch script to Steam as a non-Steam game using
absolute paths to `.venv/bin/python`, `boogie_guest.py`, and your private pairing.
Use Steam's Gamepad layout. Keep invitations out of command-line arguments. A
prebuilt Deck installer/automatic Steam shortcut is not included in this source
release.

## Controls and leave

D-pad/left stick navigates, A selects, B goes back. The persistent **Options**
button, Esc, or L3+R3 opens the local menu. **Leave session** asks for confirmation.
The emergency View+Menu hold also leaves; other participants continue playing.
Opening a menu, losing focus, disconnecting, or editing mappings releases this
guest's inputs and requires fresh neutral input before gameplay resumes.

Options → Controls identifies **your player**, game and connected devices. Pick
a device, use the step-by-step wizard or capture individual actions, replace/add
multiple bindings, and save for the session, game+device, or device. Host-requested
mapping setup opens the same local editor without changing another device's
mappings. Preferences are stored under `~/.local/share/boogie-woogie/`; no pairing
secret is persisted in those profiles. `--controls-file` can seed a validated
native button profile; menu controls and escape routes remain fixed.

## Validation and limits

```sh
.venv/bin/python -m unittest discover -p 'test_*.py'
.venv/bin/python boogie_guest.py --self-test --volume 35 --mute --show-fps
```

The source suite exercises role authority, TLS pinning/no redirects, real local
DTLS/SCTP + VP8/Opus, input release, leave confirmation, mapper scopes/wizard,
authenticated artwork bounds, SDL menu rendering, local audio gain, and CLI
rejection before media initialization. Synthetic/original fixtures are included;
no commercial-game imagery is needed. Internal tests may use loopback for their
own temporary servers; the public CLI rejects loopback pairing.

The preceding private Linux x86_64 / Steam Deck prototype was owner-tested with
Android Player 1 and native Deck Player 2. This extracted guest has passed source,
headless SDL and local transport tests on Linux x86_64 and macOS development
runtimes. The aiohttp security dependency update was rechecked with a fresh full
Linux lock installation; the macOS development results predate that dependency
update. A fresh physical Deck/Android trial of this exact source revision is
still pending. macOS desktop hardware acceptance, Windows packaging/controllers,
and fresh-install SteamOS dependency setup remain pending. See [validation
status](validation.md) before making broader device claims.

## Third-party notices

This directory ships our source and original vector/fixture assets, not SDL,
FFmpeg, Qt, aiortc wheels or emulator binaries. Preserve upstream notices and
source obligations when packaging dependencies. See [SDL3's license](https://github.com/libsdl-org/SDL/blob/release-3.2.28/LICENSE.txt),
[Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html),
[aiortc licensing](https://github.com/aiortc/aiortc/blob/main/LICENSE),
[PyAV](https://github.com/PyAV-Org/PyAV) and this repository's
[third-party notices](third-party-notices.md).
