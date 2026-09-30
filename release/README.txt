FEXTendo / PES13-NX - complete SD package

1. Extract switch/ to the root of the Switch SD card. Preserve its folders.
2. Copy your own installed PES 2013 PC v1.0 into:
   switch/pes13-fex/drive_c/PES13/
   Include pes2013.exe, the game's accompanying DLLs and img/ data.
   Keep this package's d3d9.dll, dxvk.conf and pes2013.wine-nx.txt.
3. On the Windows PC with your own PES installation, run
   source/release/tools/export-metadata.py and copy the resulting private
   pes13-install.reg into switch/pes13-fex/. This runtime still needs your
   installation metadata; it is not supplied by the release.
4. Install FEXTendo-PES13.nsp with your usual homebrew setup, then launch it.
   The NSP forwards to /switch/pes13-fex/pes13-fex.nro. Keep the SD files.
   It uses the same icon as the NRO, 32-bit no-alias address space, 4 cores
   and svcDebug disabled.

Included: production v1 NRO + startup fix, pre-DFE FEX DLL, Wine runtime,
DXVK renderers, launcher artwork/audio/fonts, all four graphics presets,
and the default Medium 720p settings.dat with compatibility copies.
Game and save directories are explicitly present even when empty.
Your game files, installation code, gameplay saves, logs and caches are
not included. Close the game before updating; back up your own settings.

The standalone NRO and NSP downloads are for updating an existing complete
installation. New installations need the -sd.zip, not just those binaries.
See manifest.json and SHA256SUMS for exact versions and hashes. Releases use
PES13 FEXTendo V.0.3.7; automatic packages add a revision such as r42.
CI checks package integrity and imports; launching still requires a Switch
hardware test. Two-player controller support is not implemented yet.

Sources, build evidence and third-party notices are included alongside switch/.
