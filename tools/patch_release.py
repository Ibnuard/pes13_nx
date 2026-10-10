"""Independent patch-release distribution; never falls back to main's runtime.

Like the original workflow this packages an approved, source-bound runtime;
it does not cross-compile an untested NRO on a public release runner.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

from pes_patch_identity import ROOT, profile, title_id, validate_catalog
from release_ci import gh, repository
from release_package import encoded, read_runtime, sha, verify_payload, verify_sources, write_zip

LOCK = ROOT / 'release/patch/runtime-lock.json'


def load_lock(path=LOCK):
    value = json.loads(path.read_text())
    if value.get('channel') != 'patch' or value.get('approved') is not True:
        raise ValueError('Patch runtime is not approved. Build and pin a patch-only input; original runtime is never substituted.')
    if (not re.fullmatch(r'runtime-patch-[A-Za-z0-9._-]+', value.get('tag', ''))
            or not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', value.get('asset', ''))
            or not re.fullmatch(r'[a-f0-9]{64}', value.get('sha256', ''))
            or not re.fullmatch(r'\d+\.\d+\.\d+-patch\d+', value.get('runtime_version', ''))):
        raise ValueError('Invalid patch runtime lock')
    if value.get('profile') != profile() or not value.get('binaries') or not value.get('source_fingerprints'):
        raise ValueError('Patch lock must bind its profile, binaries and build sources')
    return value


def merged_commit():
    if os.environ.get('GITHUB_EVENT_NAME') != 'pull_request':
        raise ValueError('Patch release requires a merged PR to patch-release')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    pr = event.get('pull_request') or {}
    base = pr.get('base') or {}
    commit = pr.get('merge_commit_sha', '')
    if (event.get('action') != 'closed' or pr.get('merged') is not True
            or base.get('ref') != profile()['branch']
            or (base.get('repo') or {}).get('full_name') != repository()
            or not re.fullmatch(r'[a-f0-9]{40}', commit)):
        raise ValueError('Patch release requires a merged PR to patch-release in this repository')
    return commit


def check_tag(tag):
    if not re.fullmatch(r'patch-v\d+\.\d+\.\d+-r[1-9]\d*', tag):
        raise ValueError('Invalid patch release tag')
    return tag


def asset_names(tag):
    check_tag(tag)
    p = profile()
    return {f'FEXTendo-PES13-{tag}-sd.zip', p['nro'], p['nsp'], 'manifest.json'}


def version():
    commit, lock = merged_commit(), load_lock()
    run = os.environ['GITHUB_RUN_NUMBER']
    if not re.fullmatch(r'[1-9]\d*', run):
        raise ValueError('Invalid workflow run number')
    tag = check_tag('patch-v' + lock['runtime_version'].split('-')[0] + '-r' + run)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write(f'version={tag}\ncommit={commit}\n')
    print(tag)


def fetch(output):
    lock = load_lock()
    if '\n' in str(output) or '\r' in str(output):
        raise ValueError('Invalid output path')
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run(['gh', 'release', 'download', lock['tag'], '--repo', repository(),
                    '--pattern', lock['asset'], '--dir', str(output)], check=True)
    path = output / lock['asset']
    if sha(path.read_bytes()) != lock['sha256']:
        raise ValueError('Patch runtime archive checksum mismatch')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
        stream.write('runtime_path=' + str(path) + '\n')


def verify_isolation(files, lock):
    p = profile()
    for name, data in files.items():
        if name.startswith('switch/') and not name.startswith(p['prefix']):
            raise ValueError('Package crosses the patch SD boundary: ' + name)
        if name.endswith('.nsp') and name != p['nsp']:
            raise ValueError('Unexpected forwarder in patch package')
        if name.startswith(p['prefix']) and not name.lower().endswith(('.rgba', '.bin', '.ttf', '.fon', '.nls')):
            if b'switch/pes13-fex' in data or 'switch/pes13-fex'.encode('utf-16le') in data:
                raise ValueError('Patch payload still references the original SD folder: ' + name)
    forwarder = json.loads(files['evidence/forwarder/build.json'])
    if (forwarder.get('title_id') != f'{title_id():016x}'
            or forwarder.get('generic_abi') != 'fxtmem-v1'
            or forwarder.get('target') != '/' + p['prefix'] + p['nro']
            or forwarder.get('channel') != 'patch'):
        raise ValueError('Patch forwarder identity or opt-in ABI mismatch')
    build = json.loads(files['evidence/patch-build.json'])
    if (not build.get('built') or build.get('edition') != 'patch'
            or build.get('version') != lock['runtime_version']
            or build.get('nro_sha256') != sha(files[p['prefix'] + p['nro']])
            or build.get('identity', {}).get('profile') != p):
        raise ValueError('Patch binary does not match the isolated build receipt')
    catalog = files['source/patch/fextendo_runtime_catalog.h']
    validate_catalog(catalog)
    if sha(catalog) != build['identity']['catalog_sha256']:
        raise ValueError('Patch Runtime Fixer catalog differs from the compiled input')
    rows = re.findall(r'\{"([^"]+)",(\d+)ull,"([0-9a-f]{64})"\}', catalog.decode())
    if not rows or len({row[0] for row in rows}) != len(rows):
        raise ValueError('Empty or duplicate patch repair catalog')
    for name, size, digest in rows:
        data = files[p['prefix'] + name]
        if len(data) != int(size) or sha(data) != digest:
            raise ValueError('Patch repair would install a different runtime file: ' + name)


def assemble(runtime, output, tag, commit):
    check_tag(tag)
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('Expected full source commit')
    lock, p = load_lock(), profile()
    verify_sources(lock)
    files = read_runtime(runtime, lock)
    verify_isolation(files, lock)
    checks = verify_payload(files, lock, p)
    files['README.txt'] = (ROOT/'release/patch/README.txt').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT/'THIRD_PARTY.md').read_bytes()
    # The approved input supplies its own config/presets: never overlay main's skeleton.
    directories = {p['prefix'] + n for n in ('drive_c/PES13/img/',
        'drive_c/KONAMI/Pro Evolution Soccer 2013/save/',
        'drive_c/users/steamuser/Documents/KONAMI/Pro Evolution Soccer 2013/save/')}
    manifest = {'channel': 'patch', 'profile': p, 'package_version': tag, 'source_commit': commit,
                'runtime_version': lock['runtime_version'], 'runtime_sha256': lock['sha256'],
                'game_included': False, 'checks': checks,
                'files': {n:sha(d) for n,d in sorted(files.items())}, 'directories': sorted(directories)}
    files['manifest.json'] = encoded(manifest)
    output.mkdir(parents=True, exist_ok=False)
    archive = output / f'FEXTendo-PES13-{tag}-sd.zip'
    write_zip(archive, files, directories)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or any(sha(z.read(n)) != digest for n,digest in manifest['files'].items()):
            raise ValueError('Patch package readback failed')
        if not directories <= set(z.namelist()):
            raise ValueError('Patch save/game directories are missing')
    (output / p['nro']).write_bytes(files[p['prefix'] + p['nro']])
    (output / p['nsp']).write_bytes(files[p['nsp']])
    (output / 'manifest.json').write_bytes(files['manifest.json'])
    (output / 'SHA256SUMS').write_text(''.join(sha(path.read_bytes())+'  '+path.name+'\n'
        for path in sorted(output.iterdir()) if path.is_file()))


def validate_assets(folder, tag, commit):
    expected = asset_names(tag)
    actual = {p.name for p in folder.iterdir()}
    if actual != expected | {'SHA256SUMS'}:
        raise ValueError('Patch release asset set mismatch')
    sums = {}
    for line in (folder / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if name not in expected or name in sums or not re.fullmatch(r'[a-f0-9]{64}', digest):
            raise ValueError('Invalid patch checksum entry')
        sums[name] = digest
    if set(sums) != expected or any(sha((folder/n).read_bytes()) != h for n,h in sums.items()):
        raise ValueError('Patch release checksum mismatch')
    value = json.loads((folder / 'manifest.json').read_text())
    if (value.get('channel') != 'patch' or value.get('profile') != profile()
            or value.get('package_version') != tag or value.get('source_commit') != commit):
        raise ValueError('Patch artifact belongs to another channel, tag or commit')
    return value


def publish(folder, tag, commit):
    if merged_commit() != commit:
        raise ValueError('Patch publish commit differs from the merged PR')
    value = validate_assets(folder, tag, commit)
    repo = repository()
    prefix = 'repos/' + repo
    refs = gh('api', prefix + '/git/matching-refs/tags/' + tag)
    refs = [r for r in refs if r['ref'] == 'refs/tags/' + tag]
    if refs:
        if refs[0]['object']['type'] != 'commit' or refs[0]['object']['sha'] != commit:
            raise ValueError('Patch tag already targets a different commit')
    else:
        gh('api', prefix + '/git/refs', '--method', 'POST', data={'ref':'refs/tags/'+tag, 'sha':commit})
    pages = gh('api', prefix + '/releases?per_page=100', '--paginate', '--slurp')
    release = next((r for page in pages for r in page if r['tag_name'] == tag), None)
    if release and not release['draft']:
        expected = {p.name:'sha256:'+sha(p.read_bytes()) for p in folder.iterdir()}
        if {a['name']:a.get('digest') for a in release['assets']} != expected:
            raise ValueError('Published patch release differs; refusing overwrite')
        print('Already published: ' + release['html_url'])
        return
    if not release:
        previous = next((r['tag_name'] for page in pages for r in page
                         if not r['draft'] and re.fullmatch(r'patch-v\d+\.\d+\.\d+-r[1-9]\d*', r['tag_name'])), None)
        note_args = {'tag_name':tag, 'target_commitish':commit}
        if previous: note_args['previous_tag_name'] = previous
        notes = gh('api', prefix + '/releases/generate-notes', '--method', 'POST',
                   data=note_args)
        body = ('PES13 **Patch edition**. Install under `switch/pes13-patch-fex/` and use '
                '`FEXTendo-PES13-Patch.nsp`. Separate launcher, Wine prefix, settings, saves, '
                'cache and repair runtime from the original `pes13-fex` installation.\n\n'
                'Requires the verified **fxtmem-v1** kernel/loader and its 39-bit low-window forwarder. '
                'Game/Kitserver assets are supplied by the user. Runtime: '+value['runtime_version']+
                '. Package checks do not replace device testing.\n\n'+notes['body'])
        release = gh('api', prefix + '/releases', '--method', 'POST', data={
            'tag_name':tag, 'target_commitish':commit, 'name':'PES13 Patch FEXTendo '+tag,
            'body':body, 'draft':True, 'prerelease':False, 'make_latest':'false'})
    subprocess.run(['gh', 'release', 'upload', tag, '--repo', repo, '--clobber',
                    *[str(p) for p in sorted(folder.iterdir())]], check=True)
    result = gh('api', prefix+'/releases/'+str(release['id']), '--method', 'PATCH',
                data={'draft':False, 'make_latest':'false'})
    print('Published: ' + result['html_url'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('version')
    sub.add_parser('check-lock')
    download = sub.add_parser('fetch'); download.add_argument('--output', type=Path, required=True)
    pack = sub.add_parser('assemble')
    pack.add_argument('--runtime', type=Path, required=True)
    pack.add_argument('--output', type=Path, required=True)
    for name in ('tag', 'commit'): pack.add_argument('--'+name, required=True)
    pub = sub.add_parser('publish'); pub.add_argument('--input', type=Path, required=True)
    for name in ('tag', 'commit'): pub.add_argument('--'+name, required=True)
    args = parser.parse_args()
    if args.command == 'version': version()
    elif args.command == 'check-lock': load_lock(); print('Patch runtime approved')
    elif args.command == 'fetch': fetch(args.output)
    elif args.command == 'assemble': assemble(args.runtime,args.output,args.tag,args.commit)
    else: publish(args.input,args.tag,args.commit)


if __name__ == '__main__': main()
