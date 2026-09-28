# Third-party components

FEXTendo / PES13-NX is a wrapper built on existing open-source projects.
Its FEX backend uses the upstream FEX-Emu engine. The older Box64 backend remains
in the repository's history and build tools. Original copyright headers and
component licenses are preserved; the project name does not replace them.

## Provenance: reused, adapted and original

| Part | How this project uses it |
| --- | --- |
| Autorun / Wine-NX and Wine | The runtime is built from the pinned Wine-NX source, with project patches. The native Horizon runtime, Wine loader, Windows API implementation and underlying platform support are inherited code, not a runtime written from scratch here. [Autorun](https://github.com/autorunhq/autorun) is the project's current name. The base is Wine-NX commit `1bc4e45163f0d2328cdfd35c7f471dd9821bb879`, recorded in [dependencies.json](dependencies.json). |
| Direct Autorun backport | The waitable-timer changes in [tools/fex_runtime_fixes.py](tools/fex_runtime_fixes.py) contain before/after code from Autorun commit [51f94949](https://github.com/autorunhq/autorun/commit/51f94949d738c978bfb80a5118d7ffa4cf6b98ae), then add project changes for cancellation semantics, bounded catch-up, overflow and rearm handling. This is adapted upstream code, not wholly original code. |
| Autorun references | Thread placement, synchronization and configuration were studied against pinned Autorun source. The [thread/CPU audit](docs/AUTORUN-THREAD-CPU-AUDIT-2026-09-28.md) distinguishes implemented behavior from unimplemented proposals. Referencing those designs does not mean their entire implementation was copied. |
| Upstream FEX-Emu | The CPU translator, JIT and upstream WOW64 implementation come from FEX-Emu and are built with Horizon-specific patches. FEX-Emu itself was not created by this project. |
| Original FEX-Emu port to Nintendo Switch | FEXTendo / AndroSwitch Project developed this port and its Horizon/Wine integration: the host adapter under [src/fex/](src/fex/), Horizon JIT-memory interface, PE/native callback ABI, Wine exception bridge, project profiles and original guest tests, plus integration/build patchers. This port integrates and modifies upstream FEX/Wine; its host adapter was independently developed, not copied from Autorun. Porting work is credited to this project; the FEX-Emu engine remains the work of its upstream authors. Project code is MIT where marked; patched upstream files retain their own notices. |
| Original FEXTendo launcher | [src/runtime/fextendo_*.h](src/runtime/) implements the native menu, renderer, focus/scroll animation, preset handling, generated audio cues, Last played history and timestamp overlay. It does not enter or copy Wine-NX's SDL launcher. The overlay uses libnx's VI protocol; [libnx VI](https://github.com/switchbrew/libnx/blob/master/nx/source/services/vi.c) and [libtesla's layer-stack setup](https://github.com/WerWolv/libtesla/blob/master/include/tesla.hpp) were engineering references. |
| Direct runtime dependencies | The package retains matched Wine modules, fonts/NLS data and DXVK DLLs from the pinned Wine-NX release payload where recorded by packaging manifests. Mesa, libnx and portlibs are linked dependencies. Building or packaging these does not make them original project code. |

PES-specific runtime changes use LGPL-2.1-or-later unless marked otherwise;
the new FEX adapter uses MIT. The complete project licenses are [LICENSE](LICENSE)
and [src/fex/LICENSE](src/fex/LICENSE). Dependency revisions are recorded in
[dependencies.json](dependencies.json), the FEX build recipes and package receipts.

## Upstream components

| Component | Attribution | License / source |
| --- | --- | --- |
| Wine / Wine-NX / Autorun | Wine authors; danfromtico and Autorun contributors | LGPL-2.1-or-later; [pinned source](https://github.com/danfromtico/wine-nx/tree/1bc4e45163f0d2328cdfd35c7f471dd9821bb879) |
| Box64 | ptitSeb and contributors | MIT; [pinned source](https://github.com/ptitSeb/box64/tree/dae0917c47b4edd8956f314210417a20fd225c4b) |
| FEX-Emu | Ryan Houdek and FEX contributors | MIT; [pinned source](https://github.com/FEX-Emu/FEX/tree/e2f973fe931e6dc2ce523795e51ca1ac3ca85816); upstream dependencies retain their individual licenses |
| DXVK | Philip Rebohle, Joshua Ashton, Robin Kertels, Jeffrey Ellison and contributors | zlib/libpng; [source](https://github.com/doitsujin/dxvk) at `878473ba`, version reported by the retained release DLL |
| Mesa / mesa-switch | Mesa authors; danfromtico, NaGaa95 and contributors | Mostly MIT, individual source licenses apply; [pinned source](https://github.com/danfromtico/mesa-switch/tree/b297e230ef88c6c88df2561becf864f979f494a6) |
| libnx | switchbrew and contributors | ISC; [source](https://github.com/switchbrew/libnx) |
| SDL2 / SDL2_ttf | Sam Lantinga and contributors | zlib; [source](https://github.com/libsdl-org) |
| FreeType | The FreeType Project | FTL or GPL-2.0; [source](https://freetype.org) |
| HarfBuzz | HarfBuzz authors | MIT; [source](https://github.com/harfbuzz/harfbuzz) |
| libdrm_nouveau | Mesa/libdrm authors and Switch port contributors | MIT, per source; devkitPro portlib |
| libpng / zlib / bzip2 | Their respective authors | libpng / zlib / BSD-style, respectively |
| Expat / Zstandard | Their respective authors | MIT / BSD-or-GPL dual license, respectively |
| devkitA64 / llvm-mingw / Rust | devkitPro, GCC, LLVM, mingw-w64 and Rust contributors | Toolchain components retain their respective licenses |

Wine fonts and NLS files are retained from the matched release dependency
package. Their source and notices are in the Wine tree. The upstream source
also contains Wine-NX's launcher implementation; PES13-NX starts PES directly
and does not enter that launcher. The Wine-NX launcher design acknowledges
[dolphin-nx](https://github.com/NaGaa95/dolphin-nx); its implementation is Wine-NX code.

[Sphaira](https://github.com/NaGaa95/sphaira), by ITotalJustice, NaGaa95 and
contributors, supplies the forwarder configuration used for the hardware run.
No Sphaira binary is included in the public PES13-NX package.

The new adapter under `src/fex/` and its JIT probe test are MIT-licensed; see
`src/fex/LICENSE`. The standalone FEX1 probe package includes the FEX MIT and
libnx ISC notices. Its retained libnx notice comes from the
[upstream license](https://github.com/switchbrew/libnx/blob/master/LICENSE.md).
The full experimental FEX DLL is not included in the FEX1 probe. The FEX2
integration test includes that DLL, matched Wine modules and their license
notices, plus notices from FEX's retained dependencies. Its x86 smoke program
is original MIT-licensed test code, not a game executable.

The earlier Fextendo v1 launcher uses Barlow Regular and SemiBold, copyright
2017 The Barlow Project Authors, under SIL Open Font License 1.1. Source:
[Google Fonts / Barlow](https://github.com/google/fonts/tree/main/ofl/barlow).
The full notice is in `assets/fonts/OFL.txt` and `licenses/Barlow-OFL.txt` in
the Fextendo package. The native launcher does not enter Wine-NX's SDL menu.

The Fextendo experimental package includes the launcher artwork supplied by
the user (`PES13WP.jpg`, `logo.png`, and `icon.png`); rights remain with their
respective owners. Game executables, match data and saved games are not
included. The font and source-code licenses do not license the PES artwork.

FEXTendo v2 and later use Inter (The Inter Project Authors) under SIL OFL 1.1:
`assets/fonts/Inter/OFL.txt`, packaged as `licenses/Inter-OFL.txt`.
The user-supplied Solid Duo controller sprites retain their original rights;
they are not covered by the source-code or font licenses. V2's generated
stadium, flat gamepad and FEXTendo wordmark have provenance and prompts in
`assets/fextendo-v2/GENERATION.md`.
