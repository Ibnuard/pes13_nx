# LW3: isolate the optional gameplay plugin

This is a one-file comparison for the supplied ISN Kitserver configuration.
It is **not a confirmed fix for 2x game speed** and contains no new NRO or DLL.
Use the existing **0.3.9-lw3** NRO, Low Window tile and boot entry.

## What the latest device log establishes

Input SHA-256: `26ea20e0b39e8d574078529485c94ed37c399edd61f532a4df93acd86649fb5c`.
The recording ends at 396.480 seconds. The user places kickoff after about
three minutes and reports that the match clock, players and ball accelerate.

- All **77** loaded WECF snapshots, from **14.642 to 396.480 seconds**, have
  `flags=0289`, `frame_skip=0`, `vsync=1`, valid CRC and 1280x720 Medium.
  This is runtime evidence, not just a settings.dat filename or template.
  It does not inspect a separate engine copy of the timing state or every
  transient between samples.
- The **24** observed clock-call targets stay at `7b80e70c` (QPF) and
  `7b80e6f8` (QPC). They match the supplied Wine kernel32 exports. The
  standard Speeder hook which replaces the game's QPF call is not visible.
  This does not prove the returned clock rate or exclude another game hook.
- `kitserver13/plugin/gameplay.dll` fails process attach with **c0000005** at
  **13.348 seconds**, while Gameplaytool.dll and the game continue. This is a
  concrete failure to isolate. Its relationship to 2x motion is not proven;
  failed initialization alone does not establish whether earlier writes ran.
- The local `gameplay.ini` specifies ball and motion speeds of 100, while
  `gameplaytool.ini` has count.factor=1 and Kitserver config.txt leaves Speeder
  at its default. These local files do not prove the SD copies are identical.

The loader reads numbered entries from `[plugin]` and ends at the first
missing entry (its default is `-1`). The supplied file has exactly two entries:
camera.dll and gameplay.dll. The overlay comments out only entry 2; it keeps
entry 1 (camera.dll). The packager rejects a different plugin list.

## Install and compare

1. Close PES via HOME -> X. Keep a backup of the SD's current
   `/switch/pes13-fex/drive_c/PES13/kitserver13/plugin.ini`.
2. Copy this package's `switch/` folder to the SD root. Replace **plugin.ini
   only**. Kitserver assets, loader, camera, settings.dat and the NRO are not
   replaced. No reboot or forwarder reinstall is required.
3. Choose **Debug launch**, keep the same preset/renderer/clocks and play a
   comparable match. Compare movement and the scoreboard advance over the
   same real-time interval of uninterrupted play at the same match duration.
   PES's accelerated match clock by itself is not an exact 2x measurement.
4. Save `switch/pes13-fex/fex-runtime.log` after closing. It should still show
   camera.dll loading, but no attempt to load `plugin/gameplay.dll`. Without
   this confirmation, do not treat the comparison as a valid isolation test.
5. If movement becomes normal, the optional gameplay plugin/init path is
   implicated. If it stays fast, keep investigating the engine timing state
   and remaining hooks; the test does not exclude all of Kitserver or FEX.

`rollback/switch/` restores the exact PC reference plugin.ini. If the SD file
was customized, restore the backup made in step 1 instead. The package does
not change `settings.dat`, force a half-speed clock, or retune FEX/DXVK.

## Loading observation

The 130-200 second window still shows file callback worker tid 84 using about
89% of a core in the recorded top-thread samples, with roughly 8.5 native
presents/s. The largest Vulkan submit totals belong to thread handle
`2601c8` (Wine tid 12), not callback handle `3981a5`. Completed-call wall time
includes waits and scheduling. It is not evidence that the callback's CPU
cost can simply be moved to the GPU. The exact hot callback function and the
user's prematch interval still require correlation; this overlay does not
claim a loading-time improvement.

## Local verification

The packager checks the exact two-plugin input, preserves every other byte,
keeps a byte-identical rollback, hashes all outputs, and verifies the source
game files remain unchanged. No game/third-party DLL is redistributed. The
existing LW3 NRO already passed its host and ARM64 binary checks. This new
configuration comparison has not been tested on Switch hardware.
