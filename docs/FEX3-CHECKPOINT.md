# FEX3 self-suspend gameplay checkpoint

Branch: `experimental/fex-core`.
Build marker: `pes13-fex3-self-suspend`.
Pinned FEX source: `e2f973fe931e6dc2ce523795e51ca1ac3ca85816`.
Native host ABI: 3.

The tester reports this is the furthest successful FEX build: PES reaches
an actual match and appears to reach around 30 FPS, with a few remaining
bugs. The report is visual and does not include a new timing log, clock
measurement, or description of the remaining bugs. Do not interpret it as
a measured 30 FPS lock or proof that every startup freeze is resolved.

This checkpoint includes the preceding FEX3 integration, memory/JIT fixes,
native private heap, performance profiles, bounded diagnostics, and the
native server's synchronous self-suspend implementation. The self-suspend
fix holds the request reply until a matching resume reduces the suspend
count to zero. Details and earlier evidence are in
[FEX3-SELF-SUSPEND.md](FEX3-SELF-SUSPEND.md).

## Exact tested artifacts

The working ZIP and its extracted payload are retained without rebuilding
or modifying them. Documentation in the ZIP reflects its pre-test state;
this checkpoint record captures the subsequent successful user report.

| Artifact | SHA-256 |
| --- | --- |
| `pes13-fex3-self-suspend.zip` | `a1ee787d1a3fbf61f8beeb815bec23e554f48c917e7808c280f88eb9fbe9d8a1` |
| `switch/pes13-fex/pes13-fex.nro` | `9149430b7be0d8abed1d9bd56ee9ce864d1c6c105fcc25dfcf021446bf37fbb9` |
| `switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll` | `097f53c9e2f5aaf4c2c7bb8ae7bcb60c18a4e02616beccc4b05f404ef90343bd` |
| `switch/pes13-fex/drive_c/windows/system32/ntdll.dll` | `6defa1aff2d74e4d0d74d2137ba1ece7224a6d89f1057c1b6e4fa287ca1ca1ac` |
| `switch/pes13-fex/configuration.ini` | `07b4aa385ce0b3627eea7f1ac3e4b0e550b6b4b5ce531e0542a04638cd2ea521` |
| Native ELF retained under `local/fex3/self-suspend/runtime/` | `0d4b59df94be834c40c29ede868dd09977f98bcc645ba5d09016a6b974d9a03e` |

Effective configuration: `run_guest_tests=0`, `fex_fast=1`, `fex_fastest=1`,
`production=1`, `profile=0`. The Fastest profile uses x87 64-bit precision
and relaxes scalar/SIMD/string TSO. Treat that profile as experimental.

## Validation and local outputs

The prior build passed 1,000 concurrent pthread suspend/resume cycles under
ASan/UBSan, eight linked ARM64 handler scenarios, and paired native-heap/profile
checks. The package contains the validation reports. Checkpoint preparation
verifies its ZIP CRC, original ZIP hash and all four extracted runtime hashes.
No new runtime optimization is introduced while checkpointing this result.

After cleanup, the only entries in `dist/` are:

```text
dist/
  pes13-fex3-self-suspend/
  pes13-fex3-self-suspend.zip
```

`dist/` and `local/` remain Git-ignored: the Git checkpoint contains source,
build/packaging tools, tests, configuration and documentation. Game files and
saved games are not part of this commit. The local build inputs and debugging
evidence under `local/` remain available.

The 170 older distribution entries were moved to
`local/archive/dist-before-fex3-self-suspend/` (about 7.25 GiB). Permanent
deletion was blocked by the tool policy, so cleanup uses a reversible archive
and does not reclaim that disk space. The archive is Git-ignored.

`python tools/package-fex3-self-suspend.py --verify-only` checks the archived
build inputs without rewriting the tested ZIP. Running it without that flag
repackages the same runtime payload with current documentation and therefore
may change the ZIP hash. It no longer needs an old distribution ZIP or creates
a rollback distribution.
