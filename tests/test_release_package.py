"""Regressions for distribution boundaries and empty-folder preservation."""
from pathlib import Path
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import release_package as package
import release_ci as ci


class PackageTests(unittest.TestCase):
    def test_source_line_endings_match_git_without_ignoring_content(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'src').mkdir()
            source = root / 'src/runtime.c'
            source.write_bytes(b'int x;\r\n')
            lock = {'source_fingerprints': package.fingerprints(root)}
            source.write_bytes(b'int x;\n')
            package.verify_sources(lock, root)
            source.write_bytes(b'int y;\n')
            with self.assertRaises(ValueError):
                package.verify_sources(lock, root)

    def test_empty_game_and_save_directories_survive_extraction(self):
        dirs = {'switch/pes13-fex/drive_c/PES13/img/',
                'switch/pes13-fex/drive_c/KONAMI/Pro Evolution Soccer 2013/save/'}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'sd.zip'
            package.write_zip(archive, {'README.txt': b'copy your game'}, dirs)
            with zipfile.ZipFile(archive) as z:
                z.extractall(root / 'unpacked')
            for d in dirs:
                self.assertTrue((root / 'unpacked' / d).is_dir())
                self.assertEqual(list((root / 'unpacked' / d).iterdir()), [])

    def test_rejects_traversal_absolute_and_windows_paths(self):
        for path in ('../keys', '/keys', 'a/../../keys', 'C:/keys', 'a\\keys', 'a//b'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                package.safe_name(path)

    def test_modified_or_added_source_requires_new_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'src').mkdir()
            (root / 'src/input.c').write_text('old controller')
            lock = {'source_fingerprints': package.fingerprints(root)}
            package.verify_sources(lock, root)
            (root / 'src/input.c').write_text('two controllers')
            with self.assertRaisesRegex(ValueError, 'rebuild'):
                package.verify_sources(lock, root)
            (root / 'src/input.c').write_text('old controller')
            (root / 'src/new.c').write_text('new feature')
            with self.assertRaises(ValueError):
                package.verify_sources(lock, root)

    def test_corrupt_and_unlisted_runtime_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for variant in ('good', 'changed', 'extra'):
                files = {'payload': b'old', 'runtime-manifest.json': package.encoded({'files': {'payload': package.sha(b'old')}})}
                if variant == 'changed':
                    files['payload'] = b'new'
                if variant == 'extra':
                    files['pes2013.exe'] = b'game'
                archive = root / (variant + '.zip')
                package.write_zip(archive, files)
                lock = {'sha256': package.sha(archive.read_bytes())}
                if variant == 'good':
                    self.assertEqual(package.read_runtime(archive, lock), {'payload': b'old'})
                else:
                    with self.assertRaisesRegex(ValueError, 'inventory'):
                        package.read_runtime(archive, lock)
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                package.read_runtime(root / 'good.zip', {'sha256': '0' * 64})

    def test_build_shell_scripts_and_wine_patches_are_fingerprinted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('tools/build-native.sh', 'tools/bootstrap-wsl.sh', 'patches/wine-nx.patch'):
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('approved build input')
            lock = {'source_fingerprints': package.fingerprints(root)}
            self.assertEqual(len(lock['source_fingerprints']), 3)
            for name in lock['source_fingerprints']:
                p = root / name
                p.write_text('modified input')
                with self.assertRaises(ValueError):
                    package.verify_sources(lock, root)
                p.write_text('approved build input')

    def test_symlink_in_dependency_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'input.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                info = zipfile.ZipInfo('link')
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                z.writestr(info, '/private/keys')
            with self.assertRaisesRegex(ValueError, 'member'):
                package.read_runtime(archive, {'sha256': package.sha(archive.read_bytes())})

    def test_publish_rejects_asset_from_another_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            files = {'FEXTendo-v0.3.7-r1-sd.zip': b'zip', 'pes13-fex.nro': b'nro',
                     'FEXTendo-PES13.nsp': b'nsp', 'manifest.json': package.encoded({
                         'package_version': 'v0.3.7-r1', 'source_commit': 'a' * 40})}
            for name, data in files.items():
                (root / name).write_bytes(data)
            (root / 'SHA256SUMS').write_text(''.join(package.sha(d) + '  ' + n + '\n' for n, d in files.items()))
            ci.validate_assets(root, 'v0.3.7-r1', 'a' * 40)
            with self.assertRaisesRegex(ValueError, 'different commit'):
                ci.validate_assets(root, 'v0.3.7-r1', 'b' * 40)
            (root / 'pes13-fex.nro').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                ci.validate_assets(root, 'v0.3.7-r1', 'a' * 40)

    def test_merged_pr_uses_its_merge_commit_and_stable_release_version(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output'
            event = Path(temp) / 'event.json'
            event.write_text(json.dumps({'action': 'closed', 'pull_request': {
                'merged': True, 'merge_commit_sha': 'a' * 40, 'head': {'sha': 'c' * 40},
                'base': {'ref': 'main', 'repo': {'full_name': 'owner/repo'}}}}))
            env = {'GITHUB_OUTPUT': str(out), 'GITHUB_EVENT_PATH': str(event),
                   'GITHUB_EVENT_NAME': 'pull_request_target', 'GITHUB_REPOSITORY': 'owner/repo',
                   'GITHUB_SHA': 'b' * 40, 'GITHUB_RUN_NUMBER': '42'}
            (Path(temp) / 'release').mkdir()
            (Path(temp) / 'release/runtime-lock.json').write_text(json.dumps({'runtime_version': '0.3.8-r6'}))
            with patch.dict(os.environ, env), patch.object(ci, 'ROOT', Path(temp)):
                ci.version()
                first = out.read_text()
                self.assertEqual(first, 'version=v0.3.8-r42\ncommit=' + 'a' * 40 + '\n')
                ci.version()
                self.assertEqual(out.read_text(), first + first)
                self.assertEqual(ci.release_title('v0.3.7'), 'PES13 FEXTendo V.0.3.7')
                self.assertEqual(ci.release_title('v0.3.7-r42'), 'PES13 FEXTendo V.0.3.7 (r42)')

    def test_releases_reject_open_unmerged_wrong_branch_and_push_events(self):
        with tempfile.TemporaryDirectory() as temp:
            event = Path(temp) / 'event.json'
            env = {'GITHUB_EVENT_PATH': str(event), 'GITHUB_REPOSITORY': 'owner/repo'}
            cases = [('pull_request_target', action, True, 'main', 'owner/repo', 'a' * 40)
                     for action in ('opened', 'reopened', 'synchronize')]
            cases += [(name, 'closed', True, 'main', 'owner/repo', 'a' * 40)
                      for name in ('push', 'pull_request', 'workflow_dispatch')]
            cases += [('pull_request_target', 'closed', merged, branch, repo, sha)
                      for merged, branch, repo, sha in (
                          (False, 'main', 'owner/repo', 'a' * 40),
                          ('true', 'main', 'owner/repo', 'a' * 40),
                          (True, 'master', 'owner/repo', 'a' * 40),
                          (True, 'main', 'another/repo', 'a' * 40),
                          (True, 'main', 'owner/repo', None),
                          (True, 'main', 'owner/repo', 'main'))]
            for name, action, merged, branch, repo, sha in cases:
                event.write_text(json.dumps({'action': action, 'pull_request': {
                    'merged': merged, 'merge_commit_sha': sha,
                    'base': {'ref': branch, 'repo': {'full_name': repo}}}}))
                with self.subTest(event=name, action=action, merged=merged, branch=branch, sha=sha), \
                        patch.dict(os.environ, {**env, 'GITHUB_EVENT_NAME': name}), \
                        self.assertRaises(ValueError):
                    ci.merged_commit()

    def test_fetch_returns_the_locked_asset_path_and_rejects_a_bad_download(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'release').mkdir()
            out = root / 'job-output'
            destination = root / 'download'
            asset = 'fextendo-runtime-keyboard-v4.zip'
            lock = {'tag': 'runtime-keyboard-v4', 'asset': asset, 'sha256': package.sha(b'approved')}
            lock_path = root / 'release/runtime-lock.json'
            lock_path.write_text(json.dumps(lock))
            def download(*args, **kwargs):
                self.assertIn(asset, args[0])
                (destination / asset).write_bytes(b'approved')
            with patch.object(ci, 'ROOT', root), patch.object(ci, 'repository', return_value='owner/repo'), \
                    patch.dict(os.environ, {'GITHUB_OUTPUT': str(out)}), \
                    patch.object(ci.subprocess, 'run', side_effect=download):
                ci.fetch(destination)
                self.assertEqual(out.read_text(), 'runtime_path=' + str(destination / asset) + '\n')
                before = out.read_text()
                lock['sha256'] = '0' * 64
                lock_path.write_text(json.dumps(lock))
                with self.assertRaisesRegex(ValueError, 'SHA256'):
                    ci.fetch(destination)
                self.assertEqual(out.read_text(), before)
                lock['asset'] = '../outside.zip'
                lock_path.write_text(json.dumps(lock))
                with self.assertRaisesRegex(ValueError, 'filename'):
                    ci.fetch(destination)

    def test_existing_tag_for_another_commit_cannot_be_published(self):
        ref = [{'ref': 'refs/tags/v0.3.7-r1', 'object': {'sha': 'b' * 40, 'type': 'commit'}}]
        with patch.object(ci, 'repository', return_value='owner/repo'), \
                patch.object(ci, 'validate_assets', return_value={}), \
                patch.object(ci, 'gh', return_value=ref) as api:
            with self.assertRaisesRegex(ValueError, 'different commit'):
                ci.publish(Path('/unused'), 'v0.3.7-r1', 'a' * 40)
            self.assertEqual(api.call_count, 1)

    def test_failed_upload_leaves_release_as_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def fake_gh(*args, data=None):
                calls.append((args, data))
                if 'matching-refs' in args[1]:
                    return [{'ref': 'refs/tags/v0.3.7-r1', 'object': {'sha': 'a' * 40, 'type': 'commit'}}]
                if '/releases?' in args[1]:
                    return [[{'id': 123, 'tag_name': 'v0.3.7-r1', 'draft': True}]]
                self.fail('Unexpected publish API call')
            with patch.object(ci, 'repository', return_value='owner/repo'), \
                    patch.object(ci, 'validate_assets', return_value={}), \
                    patch.object(ci, 'gh', side_effect=fake_gh), \
                    patch.object(ci.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'upload')):
                with self.assertRaises(subprocess.CalledProcessError):
                    ci.publish(Path(temp), 'v0.3.7-r1', 'a' * 40)
            self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
