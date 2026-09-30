# Complete launcher packages and GitHub releases

`.github/workflows/release.yml` runs for pull requests targeting `main` or
`master`, pushes to either branch, and manual preview runs. PRs upload a
downloadable Actions artifact. A successful push to `main`/`master` also creates
a tag and publishes a GitHub Release with generated changelog and the same
validated assets. Merging a PR causes that push automatically.

The automatic package version is `vYYYY.MM.DD.RUN_NUMBER` (commit date in UTC).
Reruns retain the tag and verify any already published asset rather than
overwriting it. Preview runs have a `-preview` suffix and never publish releases.
The package version is separate from the NRO's embedded runtime version, 0.3.7.

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
pipeline. It deliberately distributes the approved production-v1 NRO with the
launching fix and the pre-DFE DLL. It does not rebuild a later experimental
runtime or use an old NRO while claiming to have compiled new source.

`release/runtime-lock.json` pins an immutable input archive on the
`runtime-production-v1` dependency release, its SHA256, individual binary hashes
and runtime source fingerprints. The input includes required runtime DLLs,
assets, forwarder, licenses, modified sources and existing build/test evidence.
The matching NSP already targets the stable NRO path with the same icon,
32-bit no-alias address space, four cores and svcDebug disabled. CI checks its
identity and NCAs against the verified build receipt; it needs no console keys.

Changing runtime code, build patches or the icon without approving a new input
fails CI. For a new runtime (including future two-gamepad support), build/test
the NRO and matching DLLs first, create a new dependency tag/archive, and update
the lock in the same PR. Never just refresh fingerprints around stale binaries.
Configuration, presets and release documentation are assembled from the PR.
The initial input can be reproduced with:

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
  --runtime local/release/fextendo-runtime-production-v1.zip \
  --output dist/release-check --version local-preview \
  --commit "$(git rev-parse HEAD)"
```

## Permissions and validation

The package job has `contents: read`. Only a successful default-branch push
enables the publish job with `contents: write`. PR code never receives that
write token, and `pull_request_target` is not used. Actions are pinned to full
commit hashes and checkout does not retain credentials. The same repository's
dependency release is fetched with the standard `GITHUB_TOKEN`; no custom
PAT, signing key or self-hosted runner is needed. Private-repository fork PRs
remain subject to GitHub's normal Actions approval/access policies.

Checks cover archive inventory/hashes, source drift, settings checksum, NRO
metadata/icon, NSP content hashes/capability receipt, static Wine/FEX imports,
production launch configuration, exclusion of game/private data and ZIP
directory preservation. None substitutes for launching on a real Switch.

Publishing creates a draft, uploads all verified assets, then publishes it.
Retries can resume a draft; an existing public release is verified and left
intact. Changelog categories live in `.github/release.yml`. The workflow uses
GitHub's [generated release notes](https://docs.github.com/en/repositories/releasing-projects-on-github/automatically-generated-release-notes)
and [artifact upload](https://github.com/actions/upload-artifact).
