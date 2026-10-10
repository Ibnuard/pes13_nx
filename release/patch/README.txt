PES13 Patch - FEXTendo

This is the separate PATCH edition. Its runtime and game files live in:
  SD:/switch/pes13-patch-fex/
Its NRO is:
  SD:/switch/pes13-patch-fex/pes13-patch-fex.nro
Its HOME forwarder is:
  FEXTendo-PES13-Patch.nsp
  HOME name: PES13 Patch
  Title ID: 0583fa1de4917000

Requirements
Use the verified fxtmem-v1 kernel/loader boot environment and the supplied
39-bit low-window forwarder. The launcher validates the actual memory layout.
The ordinary original PES13 forwarder is a separate installation.

Installation
1. Copy this package's switch folder to the SD root.
2. Install the supplied patch NSP and open the PES13 Patch HOME tile.
3. Supply your own game and compatible patch files under:
     switch/pes13-patch-fex/drive_c/PES13/
   Include the patch's required dependency DLLs beside its executable when
   required. Optional Microsoft/Kitserver/game DLLs are not bundled here.
4. Supply your own installation metadata as required by the runtime.
5. Select graphics/controller/keyboard settings in this edition's launcher.

Each edition has its own Wine prefix, registry, launcher configuration,
game saves, shader cache, last-played history and runtime repair files.
An update does not migrate or overwrite the original pes13-fex installation.
Back up and copy personal saves deliberately when migrating to this edition.

Normal Launch does not write diagnostic logs. Debug launch writes evidence
under switch/pes13-patch-fex/ and closes the startup console when the game takes
the screen. Runtime Fixer uses the patch-specific pinned dependency only.

Game executables, Kitserver assets, registry, saves, keys and user logs are not
included. See manifest.json (inside the SD ZIP), manifest-patch.json,
SHA256SUMS-patch.txt and THIRD_PARTY.md for package identity,
checksums and credits. Package verification is not a Switch hardware test.

This first independent patch release is a preview. The latest LW6 device run
respected the launcher settings but crashed before kick-off. This rebuilt
edition has host/binary verification; it does not claim that crash is fixed.
