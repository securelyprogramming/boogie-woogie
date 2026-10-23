# Android app and shared co-op module

Use JDK 21, Android SDK 36 and the checked-in Gradle wrapper. Prepare the pinned runtime first using [the verified runtime instructions](../docs/runtime.md), then build:

```sh
cd android
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug :boogie:lintDebug
```

The standalone package is `com.emulatormayo.boogie`. `app` provides its launcher and icon; `boogie` contains the same native lobby, game picker, controller mapper and gameplay/session code embedded in Rommayo and Emulatormayo. Host gameplay currently supports NES with the existing FCEUmm runtime. The Android package includes only the selected pinned core. No ROM, firmware, credentials or saves are included.

Start a room with `../setup.sh --bind YOUR_COMPUTER_LAN_IPV4`. Open **Pairing / Connection setup → Import pairing file**, then import `host.json` on the host and `guest.json` on each guest through Android's document picker. Use **Import NES game** on a local standalone host, or use the connected RomM library in Rommayo. Select the game and save in **Co-op**, start multiplayer, then approve each guest.

**Player settings** provides sharp/smooth filtering, volume/mute, guest fit/stretch, defaults and game overrides. Hosting keeps the emulator's existing video geometry. Guest **Video quality** provides stream presets and FPS. Native Qt/SDL settings have their own renderer options. Each frontend lists only the options it actually implements.

Main apps include `android/boogie` as a Gradle library through a pinned Git submodule at `modules/boogie-woogie`. Run `git submodule update --init --recursive` and prepare the runtime inside that checkout. `-PboogieSource=/absolute/checkout` is an optional local-development override. The integration API launches an unexported Activity directly. Local game files are bounded, validated private copies; the original stays intact. Rommayo passes its own cookie through a same-process native API, never through an Intent or WebView. The native handoff stays in process memory and is cleared on return, logout and process restoration; no extra cookie file is written. Pairing imports cannot set a RomM cookie or change file paths.

Co-op assets live under `/boogie/` on the app asset origin, and files live under `files/boogie-woogie/`, separate from the main app library. Standalone and embedded installs have separate pairing/checkpoints. Old ignored prototype data is retained on disk during updates but is not automatically imported into the new namespace.

The custom integration Instrumentation uses a temporary sandbox and an original generated NES fixture. It checks pairing field filtering, rejected broker origins, local import/search/activation, original-file preservation, account cleanup retaining caches/checkpoints, private Activity export status and namespaced assets. Run after installing both debug APKs:

```sh
adb shell am instrument -w com.emulatormayo.boogie.test/com.emulatormayo.boogie.IntegrationSmoke
```

Public runtime-bearing releases remain pending [corresponding source provenance](../docs/third-party-notices.md). CI builds without publishing APK artifacts.
