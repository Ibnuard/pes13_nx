# PERF34 build record

This is a source and packaging migration over the validated PERF33 FASTMATH
candidate.  It does not claim a new FPS result.  The verification records the
same pinned Box64/Mesa/DXVK/audio objects and checks that the new NRO reads the
INI first and retains legacy sidecar fallback.

Hardware testing remains pending.  Compare the `config` package with the
previous PERF33 package at the same CPU/GPU/RAM clocks before attributing any
performance change to the configuration migration.
