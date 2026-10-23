# Boogie Woogie native guest

Join the Android host from a native SDL3 window using the same HTTPS/WebRTC
protocol as the browser guest. No Electron, browser shell, emulator core, ROM,
BIOS, host credential or RomM account is included.

See [native setup and controls](../docs/native-guest.md). Start with:

```sh
python3 boogie_guest.py --help
```

The `--config` file is explicitly selected by you and stays private. Keep it
outside the source checkout. This source extraction still needs a fresh physical
Deck-to-Android acceptance test; earlier prototype device trials are documented
separately in [validation](../docs/validation.md).
