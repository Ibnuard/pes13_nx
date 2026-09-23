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

Game code, assets, installation metadata and saved games belong to their
respective owners and are not part of this source repository or runtime ZIP.
