# PERF40 Switch result and next CPU candidate

Input: `C:/Users/Administrator/Documents/PES13LOGS/pes13-nx.log`, SHA-256
`8ff78fc8069797af9484b84689cb34f16addb6cbe685ac2dc6a10c3ed3259582`.
The build marker is `pes13-nx-0.2.0-perf40-early-round`; the CPU sampler is off.
This is one run of about 500 seconds, with no logged fault. The user reports a
noticeable gameplay speed increase and occasional approximately 30 FPS, with
speed still changing after free kicks and goal kicks.

The exact early block was selected once with no fingerprint rejection:
`[PERF40] early_round=1 ... selected=1 fingerprint_rejected=0`. Its PERF38
post-translation guard count changed from 114 merged guards in PERF39 to zero
in PERF40. The existing adjacent matrix patch remained active:
`[PERF19] ... applied=1 rejected=0`. These are compilation counters, not
execution counts or isolated frame-time savings.

| App uptime | Presents/s | Busy CPU cores | Host Present mean |
| ---: | ---: | ---: | ---: |
| 110 s | 26.28 | 1.69 | 1.08 ms |
| 140 s | 29.27 | 2.37 | 0.58 ms |
| 150 s | 27.86 | 2.90 | 0.76 ms |
| 160–240 s | 20.15 weighted | about 2.85 | mostly 0.5–1.5 ms |
| 250 s | 28.63 | 2.67 | 0.80 ms |
| 270–340 s | 19.88 weighted | about 2.8 | mostly below 1 ms |
| 410 s | 35.45 | 2.96 | 1.41 ms |
| 420–500 s | 19.62 weighted | about 2.9 | mostly 1–1.7 ms |

The log does not timestamp game scenes. Thus the high intervals are not proof
of sustained 30 FPS match play, and a short Present call does not measure the
whole graphics pipeline. The near-three-core load during the slow intervals
continues to make CPU translation worth optimizing.

The next captured game block, `0x112f8f0`, is a separate 232-byte x87 matrix
routine whose old 2,736-byte ARM64 output still has 54 FPCR reads and 80 FPCR
writes after 28 PERF38 guard merges. It ends at `0x112f9d8`; the existing
PERF19-patched matrix block begins at `0x112fb90`, 440 bytes later. PERF41
tests per-block FASTROUND only for this exact fingerprinted sibling, caps its
translation at the captured end, and leaves `0x112fb90` on the established
environment. The result on Switch remains to be measured.
