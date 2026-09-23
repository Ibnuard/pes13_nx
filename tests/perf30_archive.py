"""Preserve unrelated duplicate-name and GNU long-name archive members."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from perf30_archive import digest, members, records, replace

def member(name, data):
    header = (name.encode().ljust(16) + b'0'.ljust(12) + b'0'.ljust(6) +
              b'0'.ljust(6) + b'644'.ljust(8) + str(len(data)).encode().ljust(10) + b'`\n')
    assert len(header) == 60
    return header + data + (b'\n' if len(data) % 2 else b'')

names = b'a_very_long_driver_object_name.c.o/\n'
raw = (b'!<arch>\n' + member('/', b'old symbol table') + member('//', names) +
       member('vk_queue.c.o/', b'other implementation') + member('/0', b'long') +
       member('vk_queue.c.o/', b'target') + member('vk_queue.c.o/', b'target'))
key = ('vk_queue.c.o', digest(b'target'))
changed, counts = replace(raw, {key: b'instrumented-target'})
assert counts == {key: 2}
assert members(changed) == [
    ('vk_queue.c.o', digest(b'other implementation')),
    ('a_very_long_driver_object_name.c.o', digest(b'long')),
    ('vk_queue.c.o', digest(b'instrumented-target')),
    ('vk_queue.c.o', digest(b'instrumented-target')),
]
assert not any(r['rawname'] == '/' for r in records(changed))
assert next(r['data'] for r in records(changed) if r['rawname'] == '//') == names
for broken in (raw[:-1], b'not-an-archive', raw[:40]):
    try:
        records(broken)
    except (AssertionError, ValueError):
        pass
    else:
        raise AssertionError('Accepted truncated archive')
try:
    replace(raw, {('vk_queue.c.o', digest(b'absent')): b'new'})
except AssertionError:
    pass
else:
    raise AssertionError('Accepted missing replacement identity')
print('PERF30 duplicate archive identity, order, long names and truncation checks PASS')
