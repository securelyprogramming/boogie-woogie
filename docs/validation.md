# Validation status

## Historical prototype evidence

These observations were recorded during the precursor's device trials, before this standalone source extraction:

- Retroid Pocket 5 hosted NES gameplay with its physical D-pad, sticks and A/B working in the native library menus.
- Retroid Pocket 5 → Samsung Galaxy Android touch input and streamed gameplay were confirmed by the owner.
- Retroid Pocket 5 → native Qt Quick / SDL3 Steam Deck guest was confirmed by the owner in Steam Gaming Mode: separate Player 1/Player 2 characters in Battletoads, movement and jumping.
- Browser guest video and keyboard/touch input were exercised against the Android host. Physical browser-controller remapping remains a separate hardware test.
- The owner confirmed Deck native library navigation, Table/Cards picker, readable Search, retained tab focus, and exit confirmation with progress saved to RomM.

These establish that the shared approach worked on those devices. They do **not** establish that the newly extracted standalone app, imported pairing setup, main-app integration or all settings have passed those same device tests. No private device addresses, logs, credentials, game files or screenshots are included in this repository.

## Source checks

The Python suite tests admission, role grants, signaling limits, guest revocation, reset/stop, exact public routes, configuration permissions and bootstrap certificate/pairing separation. JavaScript tests cover input authority, release behavior, mappings, layout, quality, save operations and artwork validation using synthetic fixtures. They do not simulate a real Wi-Fi network, physical controller firmware, audible quality or cross-platform video performance.

Run the commands in the [README](../README.md) against the exact revision you plan to build. Record a new device result only after installing that build; identify the tested version and distinguish observed checks from owner-confirmed physical controls. Use original/synthetic imagery for public screenshots or blur all game art.

At extraction, 27 Python tests and 99 JavaScript tests passed. A temporary loopback setup smoke check also verified a certificate-trusted HTTPS connection, browser entry and capability routes, 404 responses for pairing/key routes, no pairing secrets in process output and clean Ctrl+C shutdown. That check used a newly generated room and did not restart the existing device test broker.

## Release acceptance

Before advertising a release, verify standalone setup, pairing import, local game import, host approval, Android-to-Android and Android-to-Deck Player 2 gameplay, watch-only rejection, release on disconnect, mapper scopes, quality/FPS, save continuity, exit confirmation and account/logout isolation. Run the organization's centralized scans on the proposed public revision. Native hosting and Players 3/4 are not release claims.

## Shared-module candidate checks

The extracted Android standalone app built successfully, including its integration-test APK; the shared library and app pass Android lint with zero errors. On the Retroid Pocket 5, 15 sandboxed Instrumentation checks passed for pairing field filtering, invalid origins, namespaced storage/assets, local NES import/search/activation, source-file preservation and account cleanup that preserves cached games and checkpoints. The native standalone home and Player settings dialog were opened on the actual mirrored Retroid; controls fit the landscape screen and directional menu navigation reached the dialog.

The frontend settings JavaScript test brings the JS suite to 100 passing checks. Runtime staging adds four passing rollback/policy tests to the 27 broker tests. The separate native guest extraction passes its 31 Linux/macOS development tests and SDL self-tests; see `native-guest/validation.json`. These are source/candidate checks, not a fresh end-to-end multi-device acceptance of the new main-app packaging. Main-app builds and physical join/gameplay are tracked separately.
