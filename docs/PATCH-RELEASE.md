# Original and patch editions

Work on the Kitserver/39-bit low-window edition belongs on `patch-release`.
The original production line belongs on `main`. Use topic branches and merge
PRs into the appropriate release branch; do not merge the entire patch branch
into main. Port a shared fix separately when it is appropriate for both editions.

| Identity | Original | Patch |
| --- | --- | --- |
| Release branch | `main` | `patch-release` |
| Workflow | `.github/workflows/release.yml` | `.github/workflows/patch-release.yml` |
| Trigger | Merged PR into `main` | Merged PR into `patch-release` |
| SD root | `switch/pes13-fex/` | `switch/pes13-patch-fex/` |
| NRO | `pes13-fex.nro` | `pes13-patch-fex.nro` |
| NRO title | PES13 - FEXTendo | PES13 Patch - FEXTendo |
| HOME tile | Existing original tile | PES13 Patch |
| NSP | `FEXTendo-PES13.nsp` | `FEXTendo-PES13-Patch.nsp` |
| Patch Title ID | Unchanged | `0583fa1de4917000` |
| Memory layout | Original 32-bit no-alias | 39-bit low-window, `fxtmem-v1` |
| Runtime lock | `release/runtime-lock.json` | `release/patch/runtime-lock.json` |
| Public release tags | `v0.3.x-rN` | `patch-v0.3.x-rN` |
| Runtime dependency tags | `runtime-production-*` | `runtime-patch-*` |
| GitHub Latest | Original release policy | Never replaces Latest |

Both workflows ignore direct pushes, open PRs, and unmerged PR closures. They
package the exact merge commit, not a moving branch head. Artifacts, concurrency
groups and publish scripts are separate. They share format/import validators.

The patch release asset names are `FEXTendo-PES13-patch-v*-sd.zip`,
`pes13-patch-fex.nro`, `FEXTendo-PES13-Patch.nsp`, `manifest-patch.json`,
and `SHA256SUMS-patch.txt`. The SD ZIP retains its internal `manifest.json`.
All public asset names and the Actions artifact contain the patch marker.

The patch workflow uses `pull_request` with `types: [closed]` and requires
`merged == true`. This allows it to live only on the patch branch. Unlike
`pull_request_target`, it does not load the workflow from the repository's
default branch. Both jobs check out the immutable merge commit explicitly.
Release PRs should originate from a topic branch in this repository so the
publish job can receive its scoped write permission.

The patch profile is `release/patch/channel.json`. Its Title ID is deterministic
and distinct from the known original and low-window probe/game IDs. This is
not a guarantee against every privately generated homebrew Title ID.

## Independent installations

```text
switch/
  pes13-fex/
    pes13-fex.nro
    configuration.ini
    launcher/
    drive_c/
    share/
  pes13-patch-fex/
    pes13-patch-fex.nro
    configuration.ini
    launcher/
    drive_c/
    share/
```

Each edition owns its launcher settings/history, Wine prefix, registry, saves,
shader cache, runtime-repair staging, and Debug-launch logs under its own root.
There is no automatic fallback to or migration from the original folder.
Copy game and personal saves deliberately when setting up the patch edition;
an updater must not copy a live Wine prefix over the other edition.

The patch forwarder requests the already-tested generic `fxtmem-v1` descriptor.
It does not add a per-title kernel rule. The user still needs the compatible
kernel/loader boot environment. Ordinary original forwarders remain separate.

## Build path

1. Prepare the patch runtime DLLs/assets in a clean directory. Do not use a
   user's entire game/SD directory as a release input. Rebuild any PE module
   whose compiled path still accesses the original root; relocating just its
   file does not change literals inside it.
2. Run `tools/prepare-patch-runtime-catalog.py` on that directory, choosing an
   immutable `runtime-patch-*` dependency tag. This produces the allowlisted
   repair archive and matching header. It excludes the NRO, game, registry,
   configuration, settings.dat and saves, so it can be prepared before the NRO
   without a circular checksum dependency. No upload happens in this tool.
3. Build the isolated native sources, supplying that header:

   ```sh
   python3 tools/build-pes-low-window.py --revision 6 --edition patch \
     --patch-version 0.3.9-patch1 --patch-catalog /path/to/patch-catalog.h \
     --work /path/to/fresh-patch-build
   ```

   The edition overlay changes the runtime root, launcher labels, crash paths,
   repair archive prefix and compiled catalog in the private build tree. The
   original defaults are preserved. The output is `pes13-patch-fex.nro`.
   A main/original repair catalog is rejected before compilation.
4. Build its NSP using the unchanged, verified low-window forwarder NSO:

   ```sh
   python3 tools/build-pes-low-window-forwarder.py --edition patch \
     --runtime /path/to/fresh-patch-build --work /path/to/fresh-forwarder-build \
     --output /path/to/patch-forwarder --keys /path/to/private/keys
   ```

   The destination is `sdmc:/switch/pes13-patch-fex/pes13-patch-fex.nro`.
   Metadata and Title ID differ from the original and temporary low-window NSP.
5. Deliver local test builds as copy-ready directories. GitHub distribution and
   Runtime Fixer dependency archives use ZIPs for downloading/extraction.

## Approving a release input

An unapproved patch lock blocks packaging: it is not a request for a manual
GitHub approval. `package-patch-runtime.py stage` prepares hash-verified runtime
inputs without reusing the old NRO/NSP. `seal` accepts the rebuilt patch NRO,
its matching forwarder, and checks bound to that ELF, verifies the complete
payload and repair catalog, and creates an approved lock with its archive hash.

Before the first patch release, finish the build and device checks, then prepare
an immutable complete patch runtime input. It must include:

- The patch SD tree, matching NSP, required presets/config/runtime, and licenses
  with corresponding source. No game executables, Kitserver assets, saves,
  registry, keys, or logs.
- `evidence/forwarder/build.json`: the patch `forwarder-build.json` receipt.
- `evidence/patch-build.json`: the native patch `build.json` receipt.
- `source/patch/fextendo_runtime_catalog.h`: the actual compiled repair header.
- `runtime-manifest.json` with exact file SHA256s, as used by the original input
  format; the archive itself is pinned by SHA256 in the patch lock.

Upload the validated repair dependency before enabling Runtime Fixer in a
distributed build. Pin the complete runtime archive separately in the patch
lock (`channel`, `approved`, `profile`, `tag`, `asset`, `sha256`,
`runtime_version`, `binaries`, `source_fingerprints`). Fingerprints use
`release_package.fingerprints()`; never refresh them around an old binary.

`tools/patch_release.py` refuses unapproved locks, the original branch/tag/root,
original Runtime Fixer catalogs, mismatched NRO/NSP receipts, embedded original
SD paths (including UTF-16), and a repair catalog that would replace packaged
DLLs with different versions. It does not fall back to the original release.
CI performs import/format/checksum validation, not a Switch gameplay test.

## First patch preview

The independent runtime is version `0.3.9-patch1`, based on LW6, Kit16 FEX and
Kit17 DXVK. Reused DLLs are verified against their input manifests and scanned
for original installation paths. The NRO is rebuilt with patch paths and a
separate compiled repair catalog; its NSP uses the existing verified low-window
NSO with distinct metadata and target path. Initial settings and presets select
both XInput flags with VSync on and frame skipping off.

The latest LW6 device run respected launcher settings but crashed before
kick-off. The new independent build requires Switch testing. This remains a
prerelease, carries that known issue into its manifest/release notes, and never
replaces the original Latest release. Host and ARM64 model checks verify the
packaged code and isolation, not game compatibility or performance on hardware.
