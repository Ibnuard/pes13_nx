# PERF5 Box64 compiler experiment

PERF4 failed at `rld.dll`, so the Winlator Compatible Box64 profile remains
mandatory. PERF5 copies all seven Box64 values and the ARM64 fast-suspend
`ntdll.dll` byte-for-byte from PERF3. It does not change the game's files,
settings, saves, controller mapping or graphics options.

The Release build passed `-O3` followed by `-O1` to all Box64 core and dynarec
pass files; the last optimization flag wins. PERF5 changes the final option to
`-O2` for those files in an isolated WSL build directory. The script verifies
the actual compiler commands before building and restores the source tree on
success or failure. This is an experiment: the effect on Switch has not been
measured yet.

Close PES through HOME. Extract the overlay's entire `switch` directory to
the SD root. Use the same forwarder. The log must show
`pes13-nx-0.2.0-perf5-box64-o2` and the seven Compatible Box64 values.
Test at a fixed safe CPU and RAM clock. Reach the same stadium, camera and
match situation as PERF3, then play for at least three minutes. Close through
HOME and send `switch/pes13-nx/pes13-nx.log`. If `rld.dll` fails or gameplay
regresses, restore `pes13-perf4-rollback-to-perf3.zip`.

Build in WSL:
`PES_BUILD_ROOT=/home/blekjek/pes13-build python3 tools/build-perf5-test.py`.
