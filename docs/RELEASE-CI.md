# Complete launcher packages and GitHub releases

`.github/workflows/release.yml` packages and publishes only after a pull request
is merged into `main`. It listens to `pull_request_target` with `types: [closed]`
and a `merged == true` job guard. Opening/updating a PR and pushing directly to
`main` do not run this workflow. Closing an unmerged PR skips both jobs.
There is no manual preview trigger.

Checkout, package metadata and the release tag all use the event's
`pull_request.merge_commit_sha`, so another merge cannot move the source of an
in-progress release. The package and publish jobs belong to one workflow run.

User releases use a title such as **PES13 FEXTendo V.0.3.7** and a tag such as
`v0.3.7`. Automatic package runs retain that runtime version and add a revision:
tag `v0.3.7-r42`, title **PES13 FEXTendo V.0.3.7 (r42)**. The revision is the
workflow run number, so separate merges cannot collide and reruns keep their
original tag. The displayed version comes from `release/runtime-lock.json`.
Existing published assets are verified rather than overwritten. User releases
are marked Latest; the dependency input remains a separate prerelease for CI.

## Downloads

- `FEXTendo-<version>-sd.zip`: full SD layout, including NRO and NSP, Wine/FEX
  modules, DXVK, launcher assets, all four presets and default `settings.dat`.
- `pes13-fex.nro` and `FEXTendo-PES13.nsp`: separate downloads for existing installs.
- `manifest.json` and `SHA256SUMS`: exact package contents, source commit, input
  identity and integrity checks.

The ZIP contains explicit directory entries for `drive_c/PES13/img/` and the
save directories. Git keeps their skeletons through `.gitkeep`; these placeholder
files are omitted from the ZIP, leaving real empty directories. Artifact upload
receives the finished ZIP, so it cannot silently discard those folders.

Users supply their PES 2013 PC v1.0 installation. The current runtime also
requires their own `pes13-install.reg` from `tools/export-metadata.py`. This CI
does not fabricate or redistribute installation codes. `settings.dat` and
graphics presets are included; registry files, gameplay saves, logs, cache,
game executables and data are excluded.

## Approved production input

This is **package/validation CI**, not an unattended Switch cross-compilation
pipeline. It distributes the exact tested production r6 NRO (display version
0.3.8-r6), retaining the keyboard-v4 runtime DLLs and forwarder. This adds the
memory-recovery checkpoint, grouped settings, configurable live keyboard,
quiet normal launch and optional Debug launch. Some users still report an
intermittent HIGH transition freeze; the checkpoint is not a universal fix.
It retains the existing `drive_c` layout.

`release/runtime-lock.json` pins an immutable input archive on the
`runtime-production-r6` dependency release, its SHA256, individual binary hashes
and runtime source fingerprints. The input includes required runtime DLLs,
assets, forwarder, licenses, modified sources and existing build/test evidence.
The matching NSP already targets the stable NRO path with the same icon,
32-bit no-alias address space, four cores and svcDebug disabled. CI checks its
identity and NCAs against the verified build receipt; it needs no console keys.

`tools/prepare_production_r6_runtime.py` verifies the delivered r6 package and
28 test receipts before replacing only the NRO in the immutable keyboard-v4
input. Its source-bound build receipt is retained in the dependency archive.
The NRO suffix `-r6` is independent of the workflow's package revision;
automatic tags use `v0.3.8-r<workflow run number>`.
Build text fingerprints normalize CRLF to LF, matching `.gitattributes` on
Linux CI. Runtime archives, binaries and the original build receipts retain
byte-exact SHA256 checks.

Changing runtime code, build patches or the icon without approving a new input
fails CI. For a new runtime, build/test the NRO and matching DLLs first, create
a new dependency tag/archive, and update
the lock in the same PR. Never just refresh fingerprints around stale binaries.
Configuration, presets and release documentation are assembled from the PR.
The current input replaces only the NRO in the original production dependency
archive. `tools/prepare_keyboard_runtime.py` checks the exact, previously tested
keyboard-v4 ZIP, build source hashes, ten test receipts, and unchanged dependency
hashes before generating the new archive and lock. It includes the keyboard
source delta and evidence alongside the baseline sources. To reproduce it:

```sh
git show 1e53a0c:release/runtime-lock.json > local/release/runtime-production-v1.lock.json
python3 tools/prepare_keyboard_runtime.py \
  --base local/release/fextendo-runtime-production-v1.zip \
  --base-lock local/release/runtime-production-v1.lock.json \
  --keyboard dist/pes13-fextendo-keyboard-preview-v4.zip \
  --output local/release/fextendo-runtime-keyboard-v4.zip
```

Upload the verified archive to the immutable `runtime-keyboard-v4` dependency
prerelease before merging the lock change. CI reads the asset name from the lock;
it does not assume the previous production-v1 filename.

The original production-v1 dependency can be reproduced with:

```sh
python3 tools/prepare_release_runtime.py \
  --wine-release /path/to/wine-test-build-2.zip \
  --extra-dlls /path/to/working/drive_c/windows/syswow64 \
  --output local/release/fextendo-runtime-production-v1.zip
```

This maintainer-only bootstrap also needs the production and launcher archives
named in the script, their matching native PE modules, and the verified
`dist/fextendo-forwarder/` output. It selects exact manifest-listed DLLs and
requires the historical hashes; it never copies a live SD directory wholesale.

For local package verification (Python 3.11+):

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -p 'test_release_*.py' -v
python3 tools/release_package.py \
  --runtime local/release/fextendo-runtime-keyboard-v4.zip \
  --output dist/release-check --version local-preview \
  --commit "$(git rev-parse HEAD)"
```

## Permissions and validation

The package job has `contents: read`. Only a merged PR followed by successful
package validation enables the publish job with `contents: write`. Using
`pull_request_target` allows the post-merge release to work for fork contributions
as well. Both jobs are guarded by `merged == true` and check out the accepted
merge commit, never an unmerged PR head. The version/publish helpers also reject
open, unmerged, wrong-repository and non-main events.

Actions are pinned to full commit hashes and checkout does not retain
credentials. The same repository's dependency release is fetched with the
standard `GITHUB_TOKEN`; no custom PAT, signing key or self-hosted runner is
needed. The event pattern follows GitHub's
[merged pull request workflow documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#running-your-pull_request_target-workflow-when-a-pull-request-merges).

Checks cover archive inventory/hashes, source drift, settings checksum, NRO
metadata/icon, NSP content hashes/capability receipt, static Wine/FEX imports,
production launch configuration, exclusion of game/private data and ZIP
directory preservation. None substitutes for launching on a real Switch.

Publishing creates a draft, uploads all verified assets, then publishes it.
Retries can resume a draft; an existing public release is verified and left
intact. Changelog categories live in `.github/release.yml`. The workflow uses
GitHub's [generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
and [artifact upload](https://github.com/actions/upload-artifact).
