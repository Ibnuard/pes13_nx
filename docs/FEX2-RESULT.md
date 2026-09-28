# FEX2 hardware result: original x86 guest passes

The user's Switch run supplied on 2026-09-24 completes the original i386
guest using the FEX WOW64 module. The guest log ends with
`[FEX2-GUEST] PASS all checks`; the runtime records a successful worker exit,
`[LIFECYCLE] verdict=PASS` and process exit code `0x00000000`.
`[EXIT] parked after self-terminate` is the runtime's normal terminal state;
close it through HOME after the test finishes.

The 12 guest checkpoints cover integer arithmetic, FS/TLS, SSE, x87, clock
and wait calls, guest allocation, executable mapping and CALL/RET, changing
an executable page back to writable, invalidating translated code (42 to 85),
memory release, creating an x86 worker, and that worker's TLS isolation and
termination. The native full-register exception roundtrip, callback ABI,
allocation, physical counter and compact-heap preflights also pass.

This is the first complete guest PASS after the allocation-bound, physical
counter, x18 callback ABI and compact-heap fixes. Startup now reaches FEX core
initialization, executable mappings and first x86 dispatch. The sampled
`frames=0` is expected for this console test; it is not a rendering benchmark.

## Preserved evidence

The original ZIP, both submitted logs, relevant adapter sources and build
receipts are archived under `local/fex2/hardware-pass-20260924`. Its
`hardware-result.json` records the bounded result and hashes. The ZIP's CRCs
and every manifest file hash were verified before archiving. Build-time
receipts are kept unchanged rather than retroactively changing their test
status.

| Artifact | SHA-256 |
| --- | --- |
| `pes13-fex2-heap-fix.zip` | `10b87b50a11d3a379b0e9ead1d3f328919da4698392ef6bd444c48261bd9074f` |
| `pes13-fex2.nro` | `1edc6dcdceb17973c1962116a4d6feda33f3882595a885e52594d69970b8d4f8` |
| `libwow64fex.dll` | `22ad6747d1b8a1f46e4da95eb760a7a596dadc76c8278fd9c8b62d0c677dd968` |
| `fex-smoke.exe` | `78dc72225139bc6a8fe9946fa4324b1c40842b6e0e5e7f7d629ae6a23d29e4dd` |
| Submitted `fex-guest.log` | `60ba5595269c930817b5794c407dbee8f91c2721563c39ce61c0ad8140e208f2` |
| Submitted `fex-runtime.log` | `14db4dbce7306993686b758442241345bc09d6ff18a5069aebf2531520115fe9` |

Binary hashes identify the local package associated with this run. The
submitted logs do not cryptographically attest the files installed on the SD
card. FEX is pinned to `e2f973fe931e6dc2ce523795e51ca1ac3ca85816` and rpmalloc
to `09142d726429416bfa7b459151515fe3ab7622dd`.

## Next gate

The guest exercises one worker, not concurrent exception pressure. Ordinary
exceptions currently delegate to libnx's shared dump and handler stack.
Per-thread storage must be addressed before general simultaneous fault
handling. The next test should exercise multiple workers, repeated create/exit,
code changes and handled faults with bounded deadlines and separate logs.

After that gate, integrate PES in an isolated FEX prefix and compare against
the preserved Box64 baseline at the same resolution, scene and clocks. This
run does not establish PES startup, graphics/audio compatibility, guest SEH
coverage, repeated-launch stability, or a FEX performance advantage.
