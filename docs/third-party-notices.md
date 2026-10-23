# Third-party runtime notices

Boogie Woogie's own source has the repository's MIT license. EmulatorJS and its bundled emulator cores have separate licenses; the MIT notice does not replace those licenses or establish that a combined binary distribution may be offered under MIT alone. Preserve upstream copyright/license notices when preparing and packaging the runtime.

## EmulatorJS

- Runtime: **EmulatorJS 4.2.3**, unchanged official [release archive](https://github.com/EmulatorJS/EmulatorJS/releases/tag/v4.2.3).
- Pinned archive SHA-256: `07d451bc06fa3ad04ab30d9b94eb63ac34ad0babee52d60357b002bde8f3850b`.
- Upstream source tag: [EmulatorJS/EmulatorJS v4.2.3](https://github.com/EmulatorJS/EmulatorJS/tree/v4.2.3).
- Included license: `runtime/LICENSE`, GNU GPL version 3; its upstream notice states version 3 or any later version. Preserve the full text in application packages.

## Selected NES core

- Artifact: `runtime/data/cores/fceumm-legacy-wasm.data`, unchanged within that pinned release. Its SHA-256 is recorded by preparation in `runtime/UPSTREAM.json`.
- Embedded metadata: core name `fceumm`, build version **2.0.2**, minimum EmulatorJS **4.2.2**.
- Embedded source repository: [EmulatorJS/libretro-fceumm](https://github.com/EmulatorJS/libretro-fceumm).
- Embedded license text: GNU GPL version 2, copied unmodified to `runtime/third-party/fceumm/license.txt`; its upstream filename is `Copying`. Keep that text and the embedded `core.json` / `build.json` metadata with distribution notices.
- Build project: [EmulatorJS/build](https://github.com/EmulatorJS/build). Other retained cores' repositories/license filenames are listed in `runtime/data/cores/cores.json` and each core archive's own notices. Their licenses remain applicable if those files are distributed.

## Exact corresponding source remains a release requirement

The pinned release identifies exact runtime/core binaries, but the embedded FCEUmm build metadata and build report do **not** identify an exact core source commit or complete build inputs. A repository's current default branch is not proof of the corresponding source for this binary. The native SDL prototype's separately built FCEUmm commit must not be substituted for this WebAssembly core's provenance.

Before distributing a public runtime-bearing APK or installer, obtain and retain the exact corresponding upstream source, build scripts and required notices for the actual packaged runtime and every redistributed core, then supply them through the distribution's applicable source-access mechanism. Record those verified revisions/artifacts alongside the release. Until that provenance is complete, this extraction's build validation must not be described as a cleared public binary release. No ROMs, firmware, BIOS images, keys or game artwork are supplied by preparation.
