# LW5: trace the new patch's Exhibition-to-controller failure

The device run is LW4, Medium 720p, DXVK 3.1.1, with the verified 39-bit
low-window launcher and a 3129-MiB native heap. The user confirms that the
application closes itself with a Switch error after the controller transition
freezes. The supplied crash file only contains its armed header; this does not
mean that the application did not crash.

## Evidence and comparison with the previous patch

The DirectX dependency repair has passed startup: the game reaches the menu.
At 74.443 seconds a pipe requests and receives 2,101,740 bytes. At 74.445 the
write of 1,050,870 bytes finishes successfully. No pipe read is recorded before
the runtime log ends at 111.310 seconds. Only one I/O call was recorded, below
the existing first-24 trace limit. This is a useful handoff boundary to inspect,
not proof that the pipe implementation caused the later termination.

This differs from the previous patch's failures at the same scene:

* Kit11: unsupported CreatePipe retried continuously (fixed in Kit12).
* Kit12: undersized quota blocked the serial producer before publication
  (fixed in Kit13).
* Kit13: retaining buffers after the final reader closed exhausted storage
  (fixed in Kit14).

Those changes are already present in LW4. The new run has neither their
recorded create/write retry failure nor a recorded allocation failure. Frame
presentation continues near 60/s even after asset activity drops. These are
presentation counts, not proof that the controller screen or simulation moves.
No terminal exception is captured. `scbserv.dll` attachment and `stadiumserv.dll`
dependency errors occur earlier, but the log alone does not establish them as
the cause of this scene transition.

There is a separate settings observation: the launcher writes flags 0289
(frame skipping off), but the 1.03 live structure reads 02c3 (frame skipping
on) from 15.489 seconds onward, with an invalid stored checksum. LW5 does not
write to this live structure or assert that its value explains the freeze.

## Diagnostic change

Debug launch retains up to 64 failed public NT calls in a separate fixed RAM
ring. Successful render/audio traffic cannot immediately replace them in the
ordinary recent-call ring. Every five seconds the existing worker emits up to
32 unseen failures, including status, NT service number, thread, completion
time and the first two scalar arguments. Ring overwrite, producer contention
and report caps mean this is bounded evidence, not a complete syscall trace.
An API failure is not necessarily fatal; ordinary optional-file failures are
included. Internal server routing statuses and successful timeouts are excluded.

The same worker takes a nonblocking snapshot of existing pipe endpoint state:
handle, quota, queued bytes, endpoint ownership and active I/O. Registry and
pipe locks use try-lock; contention skips the snapshot. The scan is bounded to
2048 handles and eight endpoint rows. Duplicate handles may refer to the same
pipe, so rows must not be summed as unique allocations. All logging occurs
after acquired snapshot locks are released.

There are no new game-thread waits, workers, allocations, guest-pointer reads,
pipe I/O changes, memory-size changes, clock scaling or FEX/DXVK changes.
Normal launch still emits no diagnostic SD files. Debug launch uses the
existing runtime log. This build is for isolating the crash, not a claimed fix.

## Separate comparison configuration

`kit-control/` comments only `dll = kserv` in the supplied new patch's
`kitserver13/config.txt`. It keeps the exact asset paths and other options.
This temporarily disables custom GDB kit processing, so kits can look different.
It is an isolation test, not a repaired Kitserver or a complete plugin-free run.
The exact original file is in `kit-rollback/`. No active PC game file is edited.

## Verification and device check

ASan/UBSan host checks cover 240,000 concurrent calls, retained errors after
successful-call churn, wrap/overflow, and quiet/ready/busy/bounded snapshots.
ARM64 checks execute the linked NT dispatcher, diagnostic gates, pipe snapshot,
real pipe reads/writes and handle cleanup. OS/kernel/transport are modeled;
these checks do not reproduce the PES failure on a Switch.

Copy the main `switch/` folder to SD root. Keep the existing verified low-window
HOME launcher, Medium preset, renderer and clock. Use Debug launch and repeat
Exhibition -> controller, keeping `fex-runtime.log` and `crash.log`.

If the same failure persists, save that first runtime log under another name,
copy the `switch/` folder from `kit-control/` to SD root, and repeat the same
route. Keep the second log separately. Restore the original kit configuration
with `kit-rollback/switch/`; `rollback/switch/` restores the exact LW4 NRO.
No NSP, Atmosphere change, game DLL or ZIP is included.
