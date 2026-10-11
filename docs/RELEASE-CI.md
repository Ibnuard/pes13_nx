# Original PES13 production releases

`.github/workflows/release.yml` runs after a pull request is merged into `main`.
It uses `pull_request_target: closed`, requires `merged == true`, and checks out
that event's exact `merge_commit_sha`. Direct pushes, unmerged PRs and manual
workflow events do not publish. The Kitserver `patch-release` pipeline is separate.

## v0.4.1 distribution input

`release/production-lock.json` pins the immutable
`runtime-production-v0.4.1/fextendo-runtime-production-v0.4.1.zip` dependency.
The displayed version and public tag are **0.4.1 / v0.4.1**. Published releases
are immutable; another source revision cannot overwrite the same tag.
The dependency release is a prerelease and never Latest.

`release/runtime-lock.json` remains the immutable r6 **build baseline**. It is
not overwritten by promotion. Distribution helpers prefer `production-lock.json`
when present; malformed input fails rather than silently using the old runtime.

`tools/prepare_production_v041_runtime.py` checks the exact user-tested
keyboard-frame NRO, its build inputs, eight host/ARM64/dependency test receipts,
and the automatic forwarder's actual NSP metadata. It replaces only the old
NRO/forwarder in r6, preserving every pinned runtime DLL. Corresponding sources,
licenses, historical receipts and a new promotion receipt are retained.
`release/v0.4.1-device-confirmation.json` records the user's scoped OSK confirmation;
it is separate from the original pre-device-test evidence.

The automatic NSP has stock 32-bit no-alias permissions and an `fxtauto-v1`
descriptor. Compatible FEXTendo Core Patch 1.1.0+ selects the 39-bit low window;
otherwise the same forwarder and canonical NRO work in 32-bit mode. Its HOME
name in all 16 languages is PES13-FEXTendo; CNMT version is 131072.
No console keys are needed for CI validation.

## Published artifacts

- `FEXTendo-v0.4.1-sd.zip`: complete runtime layout, one NRO, one NSP, Wine/FEX,
  DXVK, launcher assets, presets and default Medium settings.dat.
- `pes13-fex.nro` and `PES13-FEXTendo.nsp`: updates for complete installations.
- `manifest.json` and `SHA256SUMS`: merge revision, input identity and hashes.

Users supply the original PES 2013 installation and their private registry
metadata. No game EXE/data, registry codes, saves, logs or caches are included.
Explicit empty game/save directories survive ZIP extraction. The Runtime Fixer
catalog remains pinned to the compatible official v0.3.8-r9 module payload.

## Validation and publishing

CI verifies source fingerprints (build text normalized to Git LF), byte-exact
archive inventory/binaries, settings CRC, NRO metadata/icon, actual NSP contents,
Wine/FEX imports, production configuration, excluded private/game data, and ZIP
readback. Host/ARM64 models and package checks do not replace Switch testing.
The package job has contents:read; publication has contents:write only after
successful verification. Actions are pinned to full commits.

Publishing creates a draft, uploads all five verified assets, then marks it
public and Latest. Reruns can resume a draft; existing public assets must match
exactly. All version/publish helpers reject non-merged, wrong-repository or
non-main events. Future runtime changes require a newly built/tested input and
new production lock, not merely updated fingerprints around an old binary.

Local reproduction (Python 3.11+):

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_release_*.py' -v
python3 tools/prepare_production_v041_runtime.py \
  --base .cache/v041-release/fextendo-runtime-production-r6.zip \
  --candidate dist/pes13-v0.4.1-keyboard-frame \
  --forwarder dist/pes13-v0.4.1-auto \
  --output local/release/fextendo-runtime-production-v0.4.1.zip \
  --lock-output release/production-lock.json
python3 tools/release_package.py \
  --runtime local/release/fextendo-runtime-production-v0.4.1.zip \
  --output dist/release-check --version v0.4.1 --commit <full-commit-sha>
```

The input archive must be uploaded to its immutable dependency prerelease before
merging the PR. CI fetches and checks the exact filename and SHA256 from the lock.
