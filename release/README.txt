PES13-FEXTendo v0.4.2 - complete SD package

1. Extract switch/ to the root of the Switch SD card, preserving folders.
2. Copy your own installed PES 2013 PC v1.0 into:
   switch/pes13-fex/drive_c/PES13/
   Include pes2013.exe, accompanying game DLLs and the complete img/ data.
   Keep this package's d3d9.dll, dxvk.conf and pes2013.wine-nx.txt.
3. On your Windows PC, run source/release/tools/export-metadata.py and copy
   your private pes13-install.reg into switch/pes13-fex/.
4. Install PES13-FEXTendo.nsp and launch it from HOME.
   Keep /switch/pes13-fex/pes13-fex.nro at that exact path.
   Only one NRO and one forwarder are required. The forwarder uses stock
   32-bit no-alias mode, or automatically uses the 39-bit low window when
   the compatible FEXTendo Core Patch (1.1.0+) is active at boot.
   Without that active patch, use Medium or lower; HIGH is disabled.

After the splash, GUI checks validate the installation and runtime, and can
repair missing runtime files. Successful runtime verification is cached;
Maintenance > Check runtime can recheck it. The repair catalog remains pinned
to the compatible official v0.3.8-r9 DLL payload; it does not replace your game.
This package is for the original game, not the separate Kitserver edition.

Settings > Keyboard selects shortcut, activation delay and screen position.
Keyboard navigation belongs to Player 1. Optional Capture activation can come
from either controller. The keyboard is drawn into the game frame using the
Autorun approach. The latest keyboard fix was confirmed working by the user;
this does not certify every hardware, game patch or kernel combination.

Normal launch disables diagnostic file writes. Enable Show debug launch and
use its tile to collect startup/error logs when reporting a problem. Functional
saves, launcher settings and necessary runtime data may still be written.

Fastest is now the default FEX profile, independent of graphics quality,
memory patch and overclock. The package sets fex_fast=1 and fex_fastest=1.
For an existing installation, update configuration.ini as well as the NRO,
or edit the existing fex_fastest entry to 1 (do not add a duplicate key).
An explicit fex_fastest=0 still selects Fast when fex_fast=1. Restart the
application after changing this setting. This release does not change clocks
or guarantee a particular FPS on every Switch.

New installations need FEXTendo-v0.4.2-sd.zip. Standalone NRO and NSP downloads
update an existing complete installation. Close the application before updating
and back up your own saves/settings. Game files, private registry metadata,
saves, logs and caches are excluded. Sources, licenses and build/test evidence
are included. manifest.json and SHA256SUMS identify the exact contents.
