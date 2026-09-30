"""Regressions for distribution boundaries and empty-folder preservation."""
from pathlib import Path
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
            files = {'FEXTendo-v2026.09.30.1-sd.zip': b'zip', 'pes13-fex.nro': b'nro',
                     'FEXTendo-PES13.nsp': b'nsp', 'manifest.json': package.encoded({
                         'package_version': 'v2026.09.30.1', 'source_commit': 'a' * 40})}
            for name, data in files.items():
                (root / name).write_bytes(data)
            (root / 'SHA256SUMS').write_text(''.join(package.sha(d) + '  ' + n + '\n' for n, d in files.items()))
            ci.validate_assets(root, 'v2026.09.30.1', 'a' * 40)
            with self.assertRaisesRegex(ValueError, 'different commit'):
                ci.validate_assets(root, 'v2026.09.30.1', 'b' * 40)
            (root / 'pes13-fex.nro').write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                ci.validate_assets(root, 'v2026.09.30.1', 'a' * 40)

    def test_pr_and_manual_runs_always_get_preview_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            for event, ref, preview in [('pull_request', 'refs/pull/3/merge', True),
                                        ('workflow_dispatch', 'refs/heads/main', True),
                                        ('push', 'refs/heads/main', False),
                                        ('push', 'refs/heads/master', False)]:
                out = Path(temp) / (event + ref.replace('/', '-'))
                env = {'GITHUB_OUTPUT': str(out), 'GITHUB_EVENT_NAME': event,
                       'GITHUB_REF': ref, 'GITHUB_RUN_NUMBER': '42'}
                with patch.dict(os.environ, env), patch.object(ci.subprocess, 'check_output', return_value='1790726400'):
                    ci.version()
                    first = out.read_text()
                    ci.version()
                    self.assertEqual(out.read_text(), first + first)
                    self.assertEqual(first.strip().endswith('-preview'), preview)

    def test_existing_tag_for_another_commit_cannot_be_published(self):
        ref = [{'ref': 'refs/tags/v2026.09.30.1', 'object': {'sha': 'b' * 40, 'type': 'commit'}}]
        with patch.object(ci, 'repository', return_value='owner/repo'), \
                patch.object(ci, 'validate_assets', return_value={}), \
                patch.object(ci, 'gh', return_value=ref) as api:
            with self.assertRaisesRegex(ValueError, 'different commit'):
                ci.publish(Path('/unused'), 'v2026.09.30.1', 'a' * 40)
            self.assertEqual(api.call_count, 1)

    def test_failed_upload_leaves_release_as_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = []
            def fake_gh(*args, data=None):
                calls.append((args, data))
                if 'matching-refs' in args[1]:
                    return [{'ref': 'refs/tags/v2026.09.30.1', 'object': {'sha': 'a' * 40, 'type': 'commit'}}]
                if '/releases?' in args[1]:
                    return [[{'id': 123, 'tag_name': 'v2026.09.30.1', 'draft': True}]]
                self.fail('Unexpected publish API call')
            with patch.object(ci, 'repository', return_value='owner/repo'), \
                    patch.object(ci, 'validate_assets', return_value={}), \
                    patch.object(ci, 'gh', side_effect=fake_gh), \
                    patch.object(ci.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'upload')):
                with self.assertRaises(subprocess.CalledProcessError):
                    ci.publish(Path(temp), 'v2026.09.30.1', 'a' * 40)
            self.assertEqual(len(calls), 2)


if __name__ == '__main__':
    unittest.main()
