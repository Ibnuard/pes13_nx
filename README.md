# FEXTendo / PES13-NX

FEXTendo is a Nintendo Switch launcher and compatibility **wrapper for the
Windows PC version of PES 2013**. It uses Wine, FEX-Emu and DXVK to run the PC
game; this repository contains the wrapper, integration code and build tools.

The **Switch port and Horizon/Wine integration of FEX-Emu in FEXTendo** are
developed by **AndroSwitch Project / Ibnuard**. The CPU translation engine is
upstream **FEX-Emu**; the Wine/Horizon runtime foundation comes from
**Wine-NX / Autorun**. See the [FEX port source and commit record](docs/FEX-PORT-PROVENANCE.md)
for our implementation work and the components we reuse or adapt. Our initial
FEX guest PASS on Switch predates the later, explicitly credited Autorun timer
backport and CPU-placement experiments.

**Provide your own installed PES 2013 PC version 1.0.** The game executable,
game data and installation code are not supplied by this repository.

## Setup

1. Install the complete FEXTendo runtime on your SD card, then apply matching
   updates. An update-only ZIP requires the existing Wine/FEX runtime files.
2. Copy your own game installation (`pes2013.exe`, accompanying game DLLs and
   `img/`) into `switch/pes13-fex/drive_c/PES13/`.
3. On the Windows PC where PES is installed, run
   [tools/export-metadata.py](tools/export-metadata.py). Copy the resulting
   `local/config/pes13-install.reg` to `switch/pes13-fex/pes13-install.reg`.
4. Launch the matching forwarder targeting
   `sdmc:/switch/pes13-fex/pes13-fex.nro` (32-bit address space, no alias, 4 cores).

Expected layout at the SD root (runtime folders shown below come from the
complete package; keep their other supplied files):

```text
switch/pes13-fex/
├── pes13-fex.nro
├── configuration.ini
├── pes13-install.reg                 # from your own Windows installation
├── launcher/                        # FEXTendo artwork, fonts and presets
├── drive_c/
│   ├── PES13/
│   │   ├── pes2013.exe               # your PC game, version 1.0
│   │   ├── img/                     # your game data
│   │   ├── ...                      # the rest of your installed game files
│   │   ├── d3d9.dll                 # package-supplied DXVK
│   │   ├── dxvk.conf
│   │   └── pes2013.wine-nx.txt
│   ├── KONAMI/Pro Evolution Soccer 2013/settings.dat
│   ├── dxvk/d3d9.dll
│   └── windows/                     # package-supplied Wine/FEX modules
└── share/wine/                      # runtime fonts and NLS data
```

Keep the package's runtime DLLs and configuration when adding game files.
The launcher manages the canonical `drive_c/KONAMI/Pro Evolution Soccer
2013/settings.dat` and its compatibility copies. Keep installation metadata
private. Close the game before replacing runtime files.

## Credits

- **FEXTendo / AndroSwitch Project:** the FEX-Emu port to Nintendo Switch,
  including our Horizon/Wine adapter, JIT memory bridge and exception handling;
  the original native launcher and PES-specific integration.
- **[Autorun (formerly Wine-NX)](https://github.com/autorunhq/autorun), danfromtico
  and contributors:** the Wine/Horizon runtime foundation, engineering
  references and explicitly attributed runtime backports.
- **[FEX-Emu](https://github.com/FEX-Emu/FEX) and its contributors:** the upstream
  CPU translation engine used by our integration. Wine, DXVK, Mesa/mesa-switch,
  libnx and the other dependencies retain their original authorship.

See [THIRD_PARTY.md](THIRD_PARTY.md) for component origins, source revisions
and licenses. Project code uses
[LGPL-2.1-or-later](LICENSE); the new FEX adapter uses [MIT](src/fex/LICENSE).
Unofficial project; not affiliated with Konami or Nintendo.
