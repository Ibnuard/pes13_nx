"""Historical PERF35 adapter; its dispatch cleanup is already inherited.

PERF34's inherited PERF8 recipe already removes SAVE_MEM and the two counters.
The idempotent removals below are therefore no-ops against that baseline.
They must not be described as a new performance improvement.
"""
import perf34_patches

# The inherited PERF22/23 recipe asks the patch module for this profile
# adapter while preparing the retained profiler header.
adapt_profile = perf34_patches.adapt_profile


def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise AssertionError(f"{label}: expected one occurrence, found {count}")
    return text.replace(old, new, 1)


def _replace_if_present(text, old, new, label):
    count = text.count(old)
    if count > 1:
        raise AssertionError(f"{label}: expected at most one occurrence, found {count}")
    return text.replace(old, new, 1) if count else text


def _remove_dispatch_diagnostics(cmake):
    # This is the exact CMake patch block in the pinned Box64Core.cmake. It
    # reads dynablock.c, injects the hash-validation atomic, then writes the
    # generated source. Keep the source generation itself intact.
    block_counter = '''    # Count hash validations of translated blocks, reported by the runtime.
    list(REMOVE_ITEM dynarec_sources "${root}/src/dynarec/dynablock.c")
    file(READ "${root}/src/dynarec/dynablock.c" dynablock_source)
    wine_nx_box64_patch(dynablock_source
        "        //if (db->always_test) SchedYield(); // just calm down...\\n        uint32_t hash = X31_hash_code(db->x64_addr, db->x64_size);"
        "        //if (db->always_test) SchedYield(); // just calm down...\\n        extern unsigned int wine_nx_box64_block_tests;\\n        __atomic_add_fetch(&wine_nx_box64_block_tests, 1, __ATOMIC_RELAXED);\\n        uint32_t hash = X31_hash_code(db->x64_addr, db->x64_size);"
        "count block validations")
'''
    block_plain = '''    list(REMOVE_ITEM dynarec_sources "${root}/src/dynarec/dynablock.c")
    file(READ "${root}/src/dynarec/dynablock.c" dynablock_source)
'''
    # The pinned PERF11 recipe already applies the same cleanup while it
    # prepares its base source. Accept an already-clean intermediate recipe
    # so the PERF35 adapter remains composable and verify the final text.
    cmake = _replace_if_present(cmake, block_counter, block_plain,
                                "block validation counter")

    dispatch_counter = '''    wine_nx_box64_patch(dispatch_source "                native_prolog(emu, block->block);"
        "                extern unsigned long long wine_nx_box64_native_entries;\\n                __atomic_add_fetch(&wine_nx_box64_native_entries, 1, __ATOMIC_RELAXED);\\n                native_prolog(emu, block->block);" "count native dispatch entries")
'''
    cmake = _replace_if_present(cmake, dispatch_counter, "",
                                "native dispatch counter")

    cmake = _replace_if_present(
        cmake,
        "target_compile_definitions(${target}-settings INTERFACE DYNAREC SAVE_MEM WINE_NX_BOX64_DYNAREC)",
        "target_compile_definitions(${target}-settings INTERFACE DYNAREC WINE_NX_BOX64_DYNAREC)",
        "SAVE_MEM definition")
    assert "count block validations" not in cmake
    assert "count native dispatch entries" not in cmake
    assert "INTERFACE DYNAREC SAVE_MEM" not in cmake
    return cmake


def adapt(cmake, dynarec, runtime, project):
    cmake, dynarec, runtime = perf34_patches.adapt(
        cmake, dynarec, runtime, project)
    cmake = _remove_dispatch_diagnostics(cmake)
    runtime = runtime.replace(
        "pes13-nx-0.2.0-perf34-config",
        "pes13-nx-0.2.0-perf35-fast-jumptable",
    )
    return cmake, dynarec, runtime


def adapt_recipe(text):
    text = perf34_patches.adapt_recipe(text)
    for old, new in (
        ("runtime-perf34-config", "runtime-perf35-fast-jumptable"),
        ("pes13-nx-0.2.0-perf34-config",
         "pes13-nx-0.2.0-perf35-fast-jumptable"),
        ("PES13-NX PERF34 CONFIG", "PES13-NX PERF35 FAST JUMPTABLE"),
        ("local/perf34", "local/perf35"),
    ):
        text = text.replace(old, new)
    return text
