# Third-party components

PES13-NX adapts Wine-NX release 108. Wine-NX and Wine remain the underlying
Windows implementation; Box64 remains the CPU translator. Original copyright
headers in upstream source are preserved. PES-specific source in this
repository is supplied under LGPL-2.1-or-later, with the full license in LICENSE.
Dependencies retain their own licenses.

| Component | Attribution | License / source |
| --- | --- | --- |
| Wine / Wine-NX | Wine authors; danfromtico and contributors | LGPL-2.1-or-later; [pinned source](https://github.com/danfromtico/wine-nx/tree/1bc4e45163f0d2328cdfd35c7f471dd9821bb879) |
| Box64 | ptitSeb and contributors | MIT; [pinned source](https://github.com/ptitSeb/box64/tree/dae0917c47b4edd8956f314210417a20fd225c4b) |
| FEX-Emu (experimental branch) | Ryan Houdek and FEX contributors | MIT; [pinned source](https://github.com/FEX-Emu/FEX/tree/e2f973fe931e6dc2ce523795e51ca1ac3ca85816); upstream dependencies retain their individual licenses |
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

Fextendo's new native launcher uses Barlow Regular and SemiBold, copyright
2017 The Barlow Project Authors, under SIL Open Font License 1.1. Source:
[Google Fonts / Barlow](https://github.com/google/fonts/tree/main/ofl/barlow).
The full notice is in `assets/fonts/OFL.txt` and `licenses/Barlow-OFL.txt` in
the Fextendo package. The native launcher does not enter Wine-NX's SDL menu.

The Fextendo experimental package includes the launcher artwork supplied by
the user (`PES13WP.jpg`, `logo.png`, and `icon.png`); rights remain with their
respective owners. Game executables, match data and saved games are not
included. The font and source-code licenses do not license the PES artwork.

FEXTendo v2 uses Inter (The Inter Project Authors) under SIL OFL 1.1:
`assets/fonts/Inter/OFL.txt`, packaged as `licenses/Inter-OFL.txt`.
The user-supplied Solid Duo controller sprites retain their original rights;
they are not covered by the source-code or font licenses. V2's generated
stadium, flat gamepad and FEXTendo wordmark have provenance and prompts in
`assets/fextendo-v2/GENERATION.md`.
