"""Build PERF7: Compatible boot, then a faster Box64 profile for the game."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile


project = Path(__file__).resolve().parents[1]
root = Path(os.environ.get("PES_BUILD_ROOT", str(Path.home() / ".cache/pes13-nx")))
source = root / "runtime-pes13-source/wine-nx-probe"
wine_source = root / "runtime-pes13-source"
cmake_source = source / "cmake/Box64Core.cmake"
engine_source = source / "source/wow64_box64_engine.c"
dynarec_source = source / "source/wow64_box64_dynarec.c"
syscall_source = wine_source / "dlls/ntdll/unix/signal_arm64.c"
loader_source = wine_source / "dlls/ntdll/loader.c"
runtime_source = source / "source/runtime.c"
build = root / "runtime-perf7-post-init-turbo"
mesa = root / "mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib"
sdk = Path("/opt/devkitpro")
perf3 = project / "dist/perf3/switch/pes13-nx"
dest = project / "dist/perf7/switch/pes13-nx"


def replace_once(value: str, old: str, new: str) -> str:
    count = value.count(old)
    if count != 1:
        raise ValueError(f"Expected one occurrence of {old!r}, found {count}")
    return value.replace(old, new)


originals = {
    path: path.read_bytes()
    for path in (
        cmake_source, engine_source, dynarec_source, syscall_source,
        loader_source, runtime_source,
    )
}

cmake_text = originals[cmake_source].decode()

# SAVE_MEM adds a fifth jump-table level. Box64 documents it as a slower,
# memory-saving mode. PES13 is a 32-bit process and PERF3 still had over 600 MB
# free after three minutes, so prefer the four-level table used by normal
# Box64 builds.
cmake_text = replace_once(
    cmake_text,
    "target_compile_definitions(${target}-settings INTERFACE DYNAREC SAVE_MEM WINE_NX_BOX64_DYNAREC)",
    "target_compile_definitions(${target}-settings INTERFACE DYNAREC WINE_NX_BOX64_DYNAREC)",
)

# Remove two diagnostic atomics from Box64's generated dispatch/validation
# paths. The native-entry counter alone was hit 29 million times in PERF3.
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
cmake_text = replace_once(cmake_text, block_counter, block_plain)

dispatch_counter = '''    wine_nx_box64_patch(dispatch_source "                native_prolog(emu, block->block);"
        "                extern unsigned long long wine_nx_box64_native_entries;\\n                __atomic_add_fetch(&wine_nx_box64_native_entries, 1, __ATOMIC_RELAXED);\\n                native_prolog(emu, block->block);" "count native dispatch entries")
'''
cmake_text = replace_once(cmake_text, dispatch_counter, "")

engine_text = originals[engine_source].decode()
for line in (
    "        __atomic_add_fetch( &wine_nx_box64_translator_locks, 1, __ATOMIC_RELAXED );\n",
    "    __atomic_add_fetch( &wine_nx_box64_tsc_reads, 1, __ATOMIC_RELAXED );\n",
    "    __atomic_add_fetch( &wine_nx_box64_inline_unix_calls, 1, __ATOMIC_RELAXED );\n",
    "    __atomic_add_fetch( &wine_nx_box64_live_engines, 1, __ATOMIC_RELAXED );\n",
    "    __atomic_add_fetch( &wine_nx_box64_executed_total, engine->executed, __ATOMIC_RELAXED );\n",
    "    __atomic_add_fetch( &wine_nx_box64_runs_total, 1, __ATOMIC_RELAXED );\n",
    "    __atomic_sub_fetch( &wine_nx_box64_live_engines, 1, __ATOMIC_RELAXED );\n",
):
    engine_text = replace_once(engine_text, line, "")

syscall_text = originals[syscall_source].decode()
syscall_counting = '''    else
    {
        __atomic_add_fetch( &wine_nx_syscalls, 1, __ATOMIC_RELAXED );
        __atomic_add_fetch( &wine_nx_syscall_counts[syscall_id & 0x1fff], 1, __ATOMIC_RELAXED );
    }
'''
syscall_text = replace_once(syscall_text, syscall_counting, "")

# rld.dll and all code that reaches Vulkan are first translated with the
# known-good Compatible values. Once WineVulkan has attached, newly seen game
# and DXVK blocks can use Box64's normal fast settings. Already translated rld
# blocks remain untouched.
dynarec_text = originals[dynarec_source].decode()
dynarec_anchor = '''int wine_nx_box64_dynarec_init(void)
{
    /* Every run asks; once set, dynarec_ready stays. */
    if (dynarec_ready) return 1;
    pthread_once( &init_once, init_dynarec );
    return dynarec_ready;
}
'''
dynarec_turbo = dynarec_anchor + '''
void wine_nx_box64_enable_game_profile(void)
{
    box64env.dynarec_safeflags = 1;
    box64env.dynarec_fastnan = 1;
    box64env.dynarec_fastround = 1;
    box64env.dynarec_bigblock = 1;
    box64env.dynarec_strongmem = 0;
    if (&wine_nx_runtime_trace)
        wine_nx_runtime_trace( "[BOX64] post-init game profile: SAFEFLAGS=1 FASTNAN=1 FASTROUND=1 BIGBLOCK=1 STRONGMEM=0; X87DOUBLE=1 CALLRET=0 retained" );
}
'''
dynarec_text = replace_once(dynarec_text, dynarec_anchor, dynarec_turbo)

loader_text = originals[loader_source].decode()
loader_anchor = '''        wine_nx_trace( "[NXLDR] attach name=%s status=%08x base=%p",
                       namebuf, (unsigned int)nts, wm->ldr.DllBase );
        if (nts != STATUS_SUCCESS)
'''
loader_turbo = '''        wine_nx_trace( "[NXLDR] attach name=%s status=%08x base=%p",
                       namebuf, (unsigned int)nts, wm->ldr.DllBase );
        if (nts == STATUS_SUCCESS && !strcmp( namebuf, "winevulkan.dll" ))
        {
            extern void wine_nx_box64_enable_game_profile(void) __attribute__((weak));
            if (&wine_nx_box64_enable_game_profile) wine_nx_box64_enable_game_profile();
        }
        if (nts != STATUS_SUCCESS)
'''
loader_text = replace_once(loader_text, loader_anchor, loader_turbo)

runtime_text = originals[runtime_source].decode()
runtime_text = replace_once(
    runtime_text,
    "pes13-nx-0.2.0-vk1-production",
    "pes13-nx-0.2.0-perf7-post-init-turbo",
)
runtime_text = replace_once(
    runtime_text,
    "static const char runtime_environment[] =\n",
    'static const char runtime_environment[] =\n    "DXVK_SHADER_CACHE_PATH=C:\\\\dxvk-cache\\0"\n',
)
runtime_text = replace_once(
    runtime_text,
    "    mkdir( WINE_DRIVE_C, 0777 );",
    '    mkdir( WINE_DRIVE_C, 0777 );\n    mkdir( WINE_DRIVE_C "/dxvk-cache", 0777 );',
)
anchor = "        unsigned long long read_ms = &wine_nx_file_read_100ns"
metric = '''        {
            static u64 last_tick;
            static unsigned int last_presents;
            unsigned int presents = &wine_nx_vk_presents ? __atomic_load_n(&wine_nx_vk_presents, __ATOMIC_RELAXED) : 0;
            if (last_tick && now > last_tick)
            {
                unsigned long long ms = armTicksToNs(now - last_tick) / 1000000;
                log_line("[PERF7] vk_present_delta=%u interval_ms=%llu", presents - last_presents, ms);
            }
            last_tick = now;
            last_presents = presents;
        }
'''
runtime_text = replace_once(runtime_text, anchor, metric + anchor)

env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / "devkitA64"))
env["PATH"] = f"{sdk}/devkitA64/bin:{sdk}/tools/bin:" + env["PATH"]
dest.mkdir(parents=True, exist_ok=True)

try:
    cmake_source.write_text(cmake_text)
    engine_source.write_text(engine_text)
    dynarec_source.write_text(dynarec_text)
    syscall_source.write_text(syscall_text)
    loader_source.write_text(loader_text)
    runtime_source.write_text(runtime_text)

    # A clean build directory prevents stale objects compiled with SAVE_MEM.
    if build.exists():
        shutil.rmtree(build)
    subprocess.run([
        "cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
        f"-DCMAKE_TOOLCHAIN_FILE={source}/cmake/switch-devkitA64.cmake",
        f"-DWINE_NX_PE_BUILD_DIR={root}/pe",
        "-DWINE_NX_BOX64_DYNAREC=ON", "-DWINE_NX_STOCK_MESA=OFF",
        f"-DWINE_NX_MESA_SWITCH_DIR={mesa}", "-DCMAKE_BUILD_TYPE=Release",
    ], env=env, check=True)
    commands = subprocess.check_output(
        ["ninja", "-C", str(build), "-t", "commands"], env=env, text=True
    )
    box64_commands = [
        line for line in commands.splitlines()
        if "wine-nx-box64-core-pass0" in line and " -c " in line
    ]
    if not box64_commands:
        raise RuntimeError("Box64 compiler commands not found")
    if any("-DSAVE_MEM" in line or " -O1 " not in line for line in box64_commands):
        raise RuntimeError("PERF7 must use final -O1 and must not define SAVE_MEM")
    subprocess.run(
        ["cmake", "--build", str(build), "--target", "wine-nx-runtime", "-j4"],
        env=env,
        check=True,
    )
    with tempfile.TemporaryDirectory(prefix="pes13-perf7-nacp-", dir=root) as tmp:
        nacp = Path(tmp) / "perf7.nacp"
        subprocess.run([
            str(sdk / "tools/bin/nacptool"), "--create",
            "PES13-NX PERF7", "PES13-NX", "0.2.0", str(nacp),
        ], check=True)
        nro = dest / "pes13-nx.nro"
        subprocess.run([
            str(sdk / "tools/bin/elf2nro"), str(build / "wine-nx-runtime.elf"),
            str(nro), f"--nacp={nacp}", f"--icon={project}/assets/icon.jpg",
        ], check=True)
finally:
    for path, data in originals.items():
        path.write_bytes(data)

for path, data in originals.items():
    if path.read_bytes() != data:
        raise RuntimeError(f"Source was not restored: {path}")

# Preserve the known-good compatibility profile and PERF3 ARM64 fast-suspend
# ntdll byte-for-byte.
for rel in ("drive_c/PES13/pes2013.box64.txt", "drive_c/windows/system32/ntdll.dll"):
    source_file = perf3 / rel
    target = dest / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, target)
    assert target.read_bytes() == source_file.read_bytes()
for name in (
    "production.txt", "controller-gamepad.txt", "controller-keyboard.txt",
    "controller-trace.txt", "vulkan-probe.txt",
):
    shutil.copy2(project / "config" / name, dest / name)

# Disable DXVK's CPU-side limiter. FIFO presentation still provides the
# display refresh ceiling, while the limiter warning and its pacing work go
# away. DXVK loads this file from the executable's working directory.
(dest / "drive_c/PES13/dxvk.conf").write_text(
    "# PES13-NX: let the Vulkan FIFO own the 60 Hz ceiling.\n"
    "d3d9.maxFrameRate = -1\n"
)

archive = project / "dist/pes13-perf7-overlay.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(project / "dist/perf7"))
    zf.write(project / "docs/PERF7.md", "PERF7.md")
with zipfile.ZipFile(archive) as zf:
    assert zf.testzip() is None

nro_blob = (dest / "pes13-nx.nro").read_bytes()
assert nro_blob[16:20] == b"NRO0"
assert b"pes13-nx-0.2.0-perf7-post-init-turbo" in nro_blob
assert b"DXVK_SHADER_CACHE_PATH=C:" in nro_blob
print(json.dumps({
    "nro_sha256": hashlib.sha256(nro_blob).hexdigest(),
    "zip": str(archive),
    "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "perf3_compat_profile_unchanged": True,
    "perf3_ntdll_unchanged": True,
    "save_mem": False,
    "hot_diagnostic_atomics": False,
    "compatible_until_winevulkan": True,
    "post_init_game_profile": "SAFEFLAGS=1 FASTNAN=1 FASTROUND=1 BIGBLOCK=1 STRONGMEM=0",
    "dxvk_builtin_limiter": False,
    "box64_final_optimization": "-O1",
    "hardware_tested": False,
}, indent=2))
