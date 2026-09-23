# PERF34 CONFIG

PERF34 keeps the tested PERF33 FASTMATH runtime and moves boolean runtime
switches into `switch/pes13-nx/configuration.ini`.  The runtime accepts the
old `*.txt` files as a compatibility fallback, but the PERF34 packages do not
ship those sidecars.

Keys use the old filename without `.txt`, with hyphens changed to underscores:
`perf33-blocks.txt` becomes `perf33_blocks`, `no-balance.txt` becomes
`no_balance`, and so on.  Values may be `0`/`1`, `true`/`false`, `on`/`off`,
or `yes`/`no`.  Lines beginning with `#` or `;` are comments.  Unknown keys
are ignored, so developers can keep experimental notes in the same file.

The checked-in template is [`config/configuration.ini`](../config/configuration.ini);
the package builder copies it to `switch/pes13-nx/configuration.ini`.  The
`control` and `diagnostics` variants alter only their one relevant key during
packaging.

`drive_c/PES13/pes2013.box64.txt`, `pes2013.wine-nx.txt`, controller key maps,
and DXVK settings remain separate because they are structured text settings,
not boolean switches.

The `config` package is the PERF33 FASTMATH profile.  `control` disables the
PERF33 block extension, and `diagnostics` enables the existing profiler.  The
NRO is identical across the three packages; only the configuration payload
changes.
