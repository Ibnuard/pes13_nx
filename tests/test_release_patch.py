"""Patch/original release separation, wrong-branch and wrong-runtime regressions."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import patch_release as release
import pes_patch_identity as identity
import release_ci as original

spec = importlib.util.spec_from_file_location('prepare_patch_catalog', ROOT/'tools/prepare-patch-runtime-catalog.py')
catalog_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog_tool)


class PatchReleaseTests(unittest.TestCase):
    def test_branches_cannot_publish_each_others_channel(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'event.json'
            env = {'GITHUB_REPOSITORY':'Ibnuard/pes13_nx', 'GITHUB_EVENT_PATH':str(path)}
            for branch, accepted, rejected in (('main',original,release), ('patch-release',release,original)):
                env['GITHUB_EVENT_NAME'] = 'pull_request' if accepted is release else 'pull_request_target'
                event = {'action':'closed', 'pull_request':{'merged':True, 'merge_commit_sha':'a'*40,
                    'base':{'ref':branch, 'repo':{'full_name':'Ibnuard/pes13_nx'}}}}
                path.write_text(json.dumps(event))
                with patch.dict(os.environ, env):
                    self.assertEqual(accepted.merged_commit(), 'a'*40)
                    with self.assertRaises(ValueError): rejected.merged_commit()
                # The branch check must still reject the other release channel
                # even when its own event type is supplied.
                other_event = 'pull_request' if rejected is release else 'pull_request_target'
                with patch.dict(os.environ, {**env, 'GITHUB_EVENT_NAME':other_event}), self.assertRaises(ValueError):
                    rejected.merged_commit()
                with patch.dict(os.environ, {**env, 'GITHUB_EVENT_NAME':other_event}), self.assertRaises(ValueError):
                    accepted.merged_commit()
                for field, value in (('action','opened'), ('merged',False)):
                    bad = json.loads(json.dumps(event))
                    if field == 'action': bad[field] = value
                    else: bad['pull_request'][field] = value
                    path.write_text(json.dumps(bad))
                    with patch.dict(os.environ,env), self.assertRaises(ValueError): accepted.merged_commit()

    def test_unapproved_patch_lock_never_uses_main(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'lock.json'
            path.write_text(json.dumps({'channel':'patch','approved':False}))
            with self.assertRaisesRegex(ValueError,'never substituted'): release.load_lock(path)
            path.write_text((ROOT/'release/runtime-lock.json').read_text())
            with self.assertRaises(ValueError): release.load_lock(path)

    def test_namespace_and_title_id_are_distinct(self):
        p = identity.profile()
        self.assertEqual(p['prefix'], 'switch/pes13-patch-fex/')
        self.assertFalse(p['make_latest'])
        self.assertNotIn(identity.title_id(), {0x05b0354496b71000,0x059a3db219b42000,0x05c87a7fe7cff000})
        self.assertEqual(identity.title_id() & 0xfff, 0)
        with self.assertRaises(ValueError): release.asset_names('v0.3.9-r10')
        self.assertIn('pes13-patch-fex.nro', release.asset_names('patch-v0.3.9-r10'))

    def test_original_repair_catalog_is_rejected(self):
        with self.assertRaises(ValueError):
            identity.validate_catalog((ROOT/'src/runtime/fextendo_runtime_catalog.h').read_bytes())

    def test_original_paths_rejected_even_inside_utf16_binary(self):
        for files in ({'switch/pes13-fex/a':b''},
                      {'switch/pes13-patch-fex/test.dll':b'/switch/pes13-fex/config'},
                      {'switch/pes13-patch-fex/test.dll':'/switch/pes13-fex/config'.encode('utf-16le')},
                      {'FEXTendo-PES13.nsp':b''}):
            with self.assertRaises(ValueError): release.verify_isolation(files,{})

    def test_patch_catalog_excludes_game_and_settings_and_has_separate_archive_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root/'payload'
            wanted = 'drive_c/windows/system32/libwow64fex.dll'
            for name in (wanted, 'drive_c/PES13/pes2013.exe', 'drive_c/PES13/rld.dll',
                         'drive_c/PES13/settings.dat', 'user.reg', 'crash.log'):
                path = payload/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'data')
            archive, header = root/'repair.zip', root/'catalog.h'
            result = catalog_tool.prepare(payload,archive,'runtime-patch-test1',header)
            self.assertEqual(result['files'], 1)
            with zipfile.ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {'switch/pes13-patch-fex/'+wanted,'repair-manifest.json'})
            identity.validate_catalog(header.read_bytes())
            # Execute the real identity overlay against a minimal generated tree.
            source, feature = root/'native', root/'feature'
            runtime = source/'wine-nx-probe/source/runtime.c'
            runtime.parent.mkdir(parents=True); feature.mkdir()
            runtime.write_text('#define FX_APP_VERSION "0.3.9-lw6"\n#define RUNTIME_DIR "sdmc:/switch/pes13-fex"\n')
            (feature/'fextendo_ui.h').write_text('"PES13" "Starting PES13"')
            (feature/'fextendo_crash.h').write_text('"/switch/pes13-fex/crash.log"')
            (feature/'fextendo_runtime_fixer.h').write_text('"switch/pes13-fex"')
            result = identity.apply(source,feature,header,'0.3.9-patch1')
            self.assertIn('0.3.9-patch1',runtime.read_text())
            self.assertIn('sdmc:/switch/pes13-patch-fex',runtime.read_text())
            self.assertEqual((feature/'fextendo_crash.h').read_text(),'"/switch/pes13-patch-fex/crash.log"')
            self.assertEqual((feature/'fextendo_ui.h').read_text(),'"PES13 Patch" "Starting PES13 Patch"')
            self.assertEqual((feature/'fextendo_runtime_fixer.h').read_text(),'"switch/pes13-patch-fex"')
            self.assertEqual((feature/'fextendo_runtime_catalog.h').read_bytes(),header.read_bytes())
            self.assertEqual(result['channel'],'patch')
            with self.assertRaises(ValueError): identity.apply(ROOT,feature,header,'0.3.9-patch1')

    def test_artifacts_are_bound_to_channel_and_merge(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); tag='patch-v0.3.9-r10'; commit='a'*40
            def populate(channel='patch'):
                for name in release.asset_names(tag):
                    data = release.encoded({'channel':channel,'profile':identity.profile(),
                        'package_version':tag,'source_commit':commit}) if name=='manifest.json' else b'fixture'
                    (root/name).write_bytes(data)
                (root/'SHA256SUMS').write_text(''.join(release.sha((root/n).read_bytes())+'  '+n+'\n'
                    for n in sorted(release.asset_names(tag))))
            populate(); release.validate_assets(root,tag,commit)
            with self.assertRaises(ValueError): release.validate_assets(root,tag,'b'*40)
            populate('original')
            with self.assertRaises(ValueError): release.validate_assets(root,tag,commit)

    def test_patch_publish_never_takes_original_latest(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp); (folder/'asset').write_bytes(b'data')
            calls=[]
            def api(*args, data=None):
                calls.append((args,data))
                if 'matching-refs' in args[1]: return []
                if args[1].endswith('/releases?per_page=100'): return [[]]
                if args[1].endswith('/releases/generate-notes'): return {'body':'notes'}
                if args[1].endswith('/releases'): return {'id':17}
                if args[1].endswith('/releases/17'): return {'html_url':'https://example.invalid/patch'}
                return {}
            with patch.object(release,'merged_commit',return_value='a'*40), \
                 patch.object(release,'validate_assets',return_value={'runtime_version':'0.3.9-patch1'}), \
                 patch.object(release,'repository',return_value='Ibnuard/pes13_nx'), \
                 patch.object(release,'gh',side_effect=api), \
                 patch.object(release.subprocess,'run'):
                release.publish(folder,'patch-v0.3.9-r10','a'*40)
            changes=[data for args,data in calls if args[1].endswith(('/releases','/releases/17'))]
            self.assertEqual(len(changes),2)
            self.assertTrue(all(data['make_latest']=='false' for data in changes))
            self.assertTrue(changes[0]['draft'])
            self.assertFalse(changes[1]['draft'])


if __name__ == '__main__': unittest.main()
