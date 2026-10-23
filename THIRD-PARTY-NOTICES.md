# Third-party notices

The app-owned source in this checkout is MIT licensed. Runtime-bearing applications include separately licensed EmulatorJS and libretro core components; the repository's MIT license does not replace their notices or redistribution requirements.

The build is pinned to the unchanged official EmulatorJS **4.2.3** archive (SHA-256 `07d451bc06fa3ad04ab30d9b94eb63ac34ad0babee52d60357b002bde8f3850b`). Its root license is GPLv3 with the upstream version-3-or-later notice. The selected FCEUmm WebAssembly archive includes GPLv2 text and build metadata; preparation retains those exact files.

**Public runtime-bearing APK/installer release is pending exact corresponding source provenance for the packaged WebAssembly core and other redistributed components.** Successful source/build/device tests do not clear that release requirement. No such binaries are published by this source extraction.

See [complete component/source requirements](docs/third-party-notices.md) and [runtime preparation](docs/runtime.md). Preserve the generated `runtime/LICENSE`, embedded core licenses and upstream notices when packaging. No ROMs, BIOS files or game artwork are included.
