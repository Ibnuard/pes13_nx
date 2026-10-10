"""Failure-atomic guest commits and bounded memory failure evidence (Kit15)."""
import shutil


def apply(source, project):
    d = source / 'dlls/ntdll/unix'
    changed = set()
    for name in ('horizon_commit.h', 'horizon_memory_failure.h'):
        shutil.copy2(project / 'src/runtime' / name, d / name)
        changed.add('dlls/ntdll/unix/' + name)
    p = d / 'horizon.c'
    s = p.read_text()
    def one(old, new):
        nonlocal s
        assert s.count(old) == 1, (old[:100], s.count(old))
        s = s.replace(old, new)
    one('/* Views of sections with no file (horizon_mmap_section), under mapping_mutex. */',
        '#include "horizon_memory_failure.h"\n\n/* Views of sections with no file (horizon_mmap_section), under mapping_mutex. */')
    one('static int protect_range_locked( void *addr, size_t size, int prot )',
        '#include "horizon_commit.h"\n\nstatic int protect_range_locked( void *addr, size_t size, int prot )')
    begin = s.index('                if (split_reservation_mapping( mapping, start, protect_size ))')
    end = s.index('\n            }', begin)
    s = s[:begin] + '''                if (commit_reservation_mapping(mapping, start, protect_size, prot)) return -1;''' + s[end:]
    one('''        errno = map_errno;
        return -1;''', '''        errno = map_errno;
        horizon_memory_failure(3, addr, source, size, rc);
        return -1;''')
    begin = s.index('static int set_code_memory_perm(')
    end = s.index('\nstatic int map_code_memory_range_ex', begin)
    part = s[begin:end]
    assert part.count('        errno = EINVAL;') == 1
    part = part.replace('        errno = EINVAL;', '        errno = EINVAL;\n        horizon_memory_failure(4, addr, source, size, rc);')
    s = s[:begin] + part + s[end:]
    one('''        horizon_object_free( &backing_pool, backing );
        return NULL;
    }

    if (fd != -1)''', '''        horizon_object_free( &backing_pool, backing );
        horizon_memory_failure(1, NULL, NULL, size, 0);
        return NULL;
    }

    if (fd != -1)''')
    one('''        errno = ENOMEM;
        return NULL;
    }

    backing->fd = -1;''', '''        errno = ENOMEM;
        horizon_memory_failure(0, NULL, NULL, size, 0);
        return NULL;
    }

    backing->fd = -1;''')
    one('''    if (!reservation) errno = ENOMEM;
    return reservation;''', '''    if (!reservation) {
        errno = ENOMEM;
        horizon_memory_failure(2, addr, NULL, size, 0);
    }
    return reservation;''')
    p.write_text(s)
    changed.add('dlls/ntdll/unix/horizon.c')
    return changed
