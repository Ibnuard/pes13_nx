"""Validate PE32 imports, delayed imports and actually requested export forwarders."""
import argparse
import collections
import json
import struct
from pathlib import Path
import pefile

p = argparse.ArgumentParser()
p.add_argument('wine', type=Path)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--entry', action='append', help='Root EXE/DLL name; repeat for additional roots')
p.add_argument('--dxvk', action='store_true', help='Include C:\\dxvk in search order and read the staged API-set schema')
a = p.parse_args()
game = a.wine / 'drive_c/PES13'
lookup = {f.name.lower(): f for f in (a.wine / 'drive_c/windows/syswow64').iterdir() if f.is_file()}
apisets = {}
if a.dxvk:
    lookup.update({f.name.lower(): f for f in (a.wine / 'drive_c/dxvk').iterdir() if f.is_file() and f.suffix.lower() == '.dll'})
    # Namespace version 6, from the actual ARM64 schema loaded by this runtime.
    with pefile.PE(str(a.wine / 'drive_c/windows/system32/apisetschema.dll')) as schema:
        raw = next(s.get_data() for s in schema.sections if s.Name.rstrip(b'\0') == b'.apiset')
    version, size, flags, count, entries, hashes, factor = struct.unpack_from('<7I', raw)
    assert version == 6 and 28 <= size <= len(raw) and entries + count * 24 <= size
    def text_at(offset, length):
        assert not length % 2 and 0 <= offset <= offset + length <= size
        return raw[offset:offset+length].decode('utf-16le').lower()
    for i in range(count):
        flags, name_off, name_len, hashed_len, values_off, values_count = struct.unpack_from('<6I', raw, entries+i*24)
        name = text_at(name_off, name_len)
        assert values_off + values_count * 20 <= size
        for j in range(values_count):
            flags, alias_off, alias_len, value_off, value_len = struct.unpack_from('<5I', raw, values_off+j*20)
            if not alias_len and value_len:
                apisets[name + '.dll'] = text_at(value_off, value_len)
                break
lookup.update({f.name.lower(): f for f in game.iterdir() if f.suffix.lower() in ('.dll', '.exe')})
queue = collections.deque((name.lower(), False) for name in (a.entry or ['pes2013.exe', 'rld.dll']))
cache, visited, issues = {}, set(), []
api_resolutions = {}
def load(name):
    if name not in cache:
        pe = pefile.PE(str(lookup[name]))
        exports = {}
        for s in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []):
            value = s.forwarder.decode() if s.forwarder else None
            exports[s.ordinal] = value
            if s.name:
                exports[s.name.decode()] = value
        cache[name] = (pe, exports)
    return cache[name]

def resolve(module, symbol, deferred, origin, chain=()):
    if module in apisets:
        api_resolutions[module] = apisets[module]
        module = apisets[module]
    marker = (module, symbol)
    if marker in chain:
        issues.append({'kind': 'forwarder_cycle', 'module': module, 'symbol': symbol, 'from': origin, 'deferred': deferred})
        return
    if module not in lookup:
        issues.append({'kind': 'missing_module', 'module': module, 'symbol': symbol, 'from': origin, 'deferred': deferred})
        return
    queue.append((module, deferred))
    pe, exports = load(module)
    if symbol not in exports:
        issues.append({'kind': 'missing_export', 'module': module, 'symbol': symbol, 'from': origin, 'deferred': deferred})
    elif exports[symbol]:
        target, name = exports[symbol].rsplit('.', 1)
        if not target.lower().endswith('.dll'):
            target += '.dll'
        resolve(target.lower(), int(name[1:]) if name.startswith('#') else name,
                deferred, origin, chain + (marker,))

while queue:
    module, deferred = queue.popleft()
    if (module, deferred) in visited:
        continue
    visited.add((module, deferred))
    if module not in lookup:
        issues.append({'kind': 'missing_module', 'module': module, 'from': 'root', 'deferred': deferred})
        continue
    pe, _ = load(module)
    if pe.FILE_HEADER.Machine != 0x14c:
        issues.append({'kind': 'wrong_machine', 'module': module, 'machine': hex(pe.FILE_HEADER.Machine), 'deferred': deferred})
    for field, delay in [('DIRECTORY_ENTRY_IMPORT', False), ('DIRECTORY_ENTRY_DELAY_IMPORT', True)]:
        for entry in getattr(pe, field, []):
            target = entry.dll.decode().lower()
            for symbol in entry.imports:
                name = symbol.name.decode() if symbol.name else symbol.ordinal
                resolve(target, name, deferred or delay, module)

for pe, _ in cache.values():
    pe.close()
report = {'checked_pe_files': len(cache),
          'missing_required_modules': sorted({i['module'] for i in issues if i['kind'] == 'missing_module' and not i['deferred']}),
          'missing_deferred_modules': sorted({i['module'] for i in issues if i['kind'] == 'missing_module' and i['deferred']}),
          'issues': issues, 'static_link_check_passed': not issues,
          'renderer': 'DXVK search path' if a.dxvk else 'WineD3D search path',
          'api_set_resolutions': api_resolutions,
          'limits': 'Checks reachable normal/delay imports and requested forwarders. Dynamic loads, COM registration, API behavior and hardware execution remain unverified. DXVK mode resolves default API-set hosts from the staged schema; other modes leave API-set names unresolved.'}
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k:v for k,v in report.items() if k != 'issues'}, indent=2))
print('Issue count:', len(issues))
raise SystemExit(0 if not issues else 1)
