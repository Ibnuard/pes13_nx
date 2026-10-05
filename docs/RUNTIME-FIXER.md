# Runtime Fixer

The 0.3.9-fixer1 NRO adds Settings > Maintenance > Runtime Fixer:

- **Check runtime**: offline SHA256 verification; no diagnostic file writes.
- **Repair runtime**: rechecks, downloads the pinned official release over
  HTTPS if needed, verifies the archive and every staged file, then replaces
  only the missing/damaged runtime files.

It uses the published `v0.3.8-r9` SD package, whose runtime DLLs match this NRO.
It does not follow `latest`. The download is about 80 MB; allow 300 MB of free
SD space for a complete repair. Only Wine DLLs, Wine fonts/NLS and the two
bundled renderer source folders are eligible. Renderer preparation installs
the user's selected renderer before launch, as it already did in r6.

Game executables, accompanying game/patch DLLs, `img/`, saves, `settings.dat`,
registry files, launcher choices, installation metadata and the installed NRO
are excluded. A missing DLL belonging to a game or patch still needs the
user's own installation. This feature cannot identify antivirus as the cause.

The operation uses the existing launcher main/UI threads and releases its
network resources before Wine starts. There is no gameplay repair worker or
background download. Normal production launch remains diagnostically quiet.

Cancellation is available while checking, downloading or staging. During
installation the UI says **Finishing safely**. A durable journal and same-card
backups permit rollback after interruption; startup completes recovery before
launch. Keep `.runtime-fixer` if recovery reports an error. Do not change NRO
versions during an interrupted repair. The journal is tied to the compiled
catalog. Unknown paths are never extracted, and corrupt downloads never enter
the installation phase.

Build with `tools/build-fextendo-input-fix.py` using the immutable keyboard-v4
source archive and the production memory-recovery switches. The new static
dependencies are devkitPro `switch-curl` (libnx TLS backend) and MiniZip from
`switch-zlib`.
`tools/runtime_fixer_catalog.py` reproduces the allowlist from the pinned GitHub
release archive. The original r6 memory, FEX and rendering behavior is retained.

Host filesystem tests inject write/rename/commit failures and process exits,
then restart recovery; these are not a physical Switch SD power-loss test.
Wi-Fi/firmware TLS and launch after repair still require device validation.
