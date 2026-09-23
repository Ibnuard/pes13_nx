"""Build PERF8: repair mutex handling, per-block policy, low-rate telemetry."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
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
vulkan_source = wine_source / "dlls/win32u/vulkan.c"
runtime_source = source / "source/runtime.c"
build = root / "runtime-perf8-block-profile"
mesa = root / "mesa-vulkan/install/opt/devkitpro/portlibs/switch/lib"
sdk = Path("/opt/devkitpro")
perf3 = project / "dist/perf3/switch/pes13-nx"
dest = project / "dist/perf8/switch/pes13-nx"


def replace_once(value: str, old: str, new: str) -> str:
    count = value.count(old)
    if count != 1:
        raise ValueError(f"Expected one occurrence of {old!r}, found {count}")
    return value.replace(old, new)


originals = {
    path: path.read_bytes()
    for path in (
        cmake_source, engine_source, dynarec_source, syscall_source,
        vulkan_source, runtime_source,
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
# Remove the whole diagnostic conditional, not just its body: otherwise the
# next real mutex_lock is accidentally conditional, with ret uninitialized.
engine_text = replace_once(engine_text, """#ifdef WINE_NX_BOX64_DYNAREC
    if (mutex == &core_context.mutex_dyndump)
        __atomic_add_fetch( &wine_nx_box64_translator_locks, 1, __ATOMIC_RELAXED );
#endif
""", "")
for line in (
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

# Select the environment in FillBlock's real compilation path, under the
# translator mutex. Only BIGBLOCK has a verified per-block override in this
# pinned Box64. Keep global math/ordering settings immutable and Compatible.
dynarec_text = originals[dynarec_source].decode()
dynarec_text = replace_once(dynarec_text,
    "unsigned long long wine_nx_box64_native_entries;",
    f'#include "{project}/src/runtime/pes13_perf8_profile.h"\n'
    "unsigned long long wine_nx_box64_native_entries;")
dynarec_text = replace_once(dynarec_text,
    "box64env_t *GetCurEnvByAddr( uintptr_t addr ) { (void)addr; return &box64env; }",
    "box64env_t *GetCurEnvByAddr( uintptr_t addr ) { return pes13_perf8_select_env(addr); }")
dynarec_text = replace_once(dynarec_text,
    "    apply_box64_options();",
    """    apply_box64_options();
    {
        FILE *profile = fopen("sdmc:/switch/pes13-nx/perf8-turbo.txt", "r");
        if (profile) { pes13_perf8_enabled = fgetc(profile) != '0'; fclose(profile); }
        if (&wine_nx_runtime_trace)
            wine_nx_runtime_trace(pes13_perf8_enabled
                ? "[BOX64] PERF8 block profile armed; waiting for a successful Vulkan present"
                : "[BOX64] PERF8 block profile disabled; Compatible control run");
    }""")

vulkan_text = originals[vulkan_source].decode()
vulkan_text = replace_once(vulkan_text, "unsigned int wine_nx_vk_presents;", """unsigned int wine_nx_vk_presents;
unsigned int wine_nx_vk_successful_presents, wine_nx_vk_host_present_calls;
unsigned long long wine_nx_vk_host_present_ticks;
extern unsigned long long wine_nx_perf8_tick(void);""")
vulkan_text = replace_once(vulkan_text,
    "    if (res == VK_SUCCESS && presents > 4 && presents % 1800) return;",
    """    if (count && (res == VK_SUCCESS || res == VK_SUBOPTIMAL_KHR))
        __atomic_add_fetch(&wine_nx_vk_successful_presents, 1, __ATOMIC_RELEASE);
    if (res == VK_SUCCESS && presents > 4 && presents % 1800) return;""")
vulkan_text = replace_once(vulkan_text,
    "    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );",
    """#ifdef __SWITCH__
    {
        unsigned long long begin = wine_nx_perf8_tick();
        res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );
        __atomic_add_fetch(&wine_nx_vk_host_present_ticks, wine_nx_perf8_tick() - begin, __ATOMIC_RELAXED);
        __atomic_add_fetch(&wine_nx_vk_host_present_calls, 1, __ATOMIC_RELAXED);
    }
#else
    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );
#endif""")

runtime_text = originals[runtime_source].decode()
runtime_text = replace_once(
    runtime_text,
    "pes13-nx-0.2.0-vk1-production",
    "pes13-nx-0.2.0-perf8-block-profile",
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
# Independent ten-second metrics; don't wait for the old 120-second report.
metrics = r"""
static void log_line(const char *fmt, ...);
unsigned long long wine_nx_perf8_tick(void) { return armGetSystemTick(); }

static void runtime_perf8_report(void)
{
    extern unsigned int wine_nx_vk_successful_presents, wine_nx_vk_host_present_calls;
    extern unsigned long long wine_nx_vk_host_present_ticks;
    extern void wine_nx_box64_profile_status(char *, size_t);
    extern void wine_nx_thread_report(void);
    static u64 start, last_tick, last_host_ticks;
    static unsigned int last_frames, last_host_calls;
    u64 now = armGetSystemTick();
    u64 host_ticks = __atomic_load_n(&wine_nx_vk_host_present_ticks, __ATOMIC_RELAXED);
    unsigned int frames = __atomic_load_n(&wine_nx_vk_successful_presents, __ATOMIC_ACQUIRE);
    unsigned int host_calls = __atomic_load_n(&wine_nx_vk_host_present_calls, __ATOMIC_RELAXED);
    if (last_tick && now > last_tick)
    {
        double ms = armTicksToNs(now - last_tick) / 1000000.0;
        unsigned int delta = frames - last_frames, calls = host_calls - last_host_calls;
        double host_ms = armTicksToNs(host_ticks - last_host_ticks) / 1000000.0;
        char profile[320];
        wine_nx_box64_profile_status(profile, sizeof(profile));
        log_line("[PERF8] uptime_s=%llu interval_ms=%.0f presents=%u fps=%.2f avg_frame_ms=%.2f host_present_calls=%u host_present_ms_per_call=%.3f %s",
                 (unsigned long long)(armTicksToNs(now - start) / 1000000000ull),
                 ms, delta, delta * 1000.0 / ms, delta ? ms / delta : 0.0,
                 calls, calls ? host_ms / calls : 0.0, profile);
    }
    if (!start) start = now;
    last_tick = now;
    last_frames = frames;
    last_host_ticks = host_ticks;
    last_host_calls = host_calls;
    wine_nx_thread_report();
}

"""
runtime_text = replace_once(runtime_text,
    "static void *log_flusher( void *arg )", metrics + "static void *log_flusher( void *arg )")
runtime_text = replace_once(runtime_text,
    "    (void)arg;\n    for (;;)\n    {\n        svcSleepThread( 200000000LL );",
    "    (void)arg;\n    runtime_perf8_report();\n    for (;;)\n    {\n        svcSleepThread( 200000000LL );")
runtime_text = replace_once(runtime_text,
    "        ++ticks;", "        ++ticks;\n        if (ticks % 50 == 0) runtime_perf8_report();")
runtime_text = replace_once(runtime_text, "            wine_nx_thread_report();", "            /* PERF8 owns the thread-report interval. */")

# Exercise the actual generated lock function and actual pinned Box64 macro.
assert "if (!BOX64DRENV(dynarec_bigblock))" in (
    source / "vendor/box64/src/dynarec/dynarec_native.c").read_text()
with tempfile.TemporaryDirectory(prefix="pes13-perf8-test-", dir=root) as tmp:
    tmp = Path(tmp)
    policy = tmp / "policy"
    subprocess.run(["cc", "-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror",
                    f"-I{source}/vendor/box64/src/include",
                    str(project / "tests/perf8_policy.c"), "-o", str(policy)], check=True)
    subprocess.run([str(policy)], check=True)
    subprocess.run([str(policy), "off"], check=True)
    begin = engine_text.index("int wine_nx_box64_mutex_lock(")
    end = engine_text.index("/* Hook added", begin)
    lock_test = tmp / "lock.c"
    lock_test.write_text('''#include <assert.h>
#include <errno.h>
#include <pthread.h>
static struct { pthread_mutex_t *held_mutex; } engine, *active_engine = &engine;
''' + engine_text[begin:end] + '''
int main(void) {
    pthread_mutex_t translation = PTHREAD_MUTEX_INITIALIZER;
    pthread_mutex_t other = PTHREAD_MUTEX_INITIALIZER;
    pthread_mutex_t *locks[] = { &translation, &other };
    for (int i = 0; i < 2; ++i) {
        assert(wine_nx_box64_mutex_lock(locks[i]) == 0);
        assert(engine.held_mutex == locks[i]);
        assert(pthread_mutex_trylock(locks[i]) == EBUSY);
        assert(wine_nx_box64_mutex_unlock(locks[i]) == 0);
        assert(engine.held_mutex == 0);
        assert(pthread_mutex_trylock(locks[i]) == 0);
        assert(pthread_mutex_unlock(locks[i]) == 0);
    }
    return 0;
}
''')
    subprocess.run(["cc", "-DWINE_NX_BOX64_DYNAREC", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-pthread", str(lock_test), "-o", str(tmp / "lock")], check=True)
    subprocess.run([str(tmp / "lock")], check=True)
print("PERF8 policy on/off and unconditional mutex locking: PASS", flush=True)
if "--check" in sys.argv:
    raise SystemExit(0)

env = dict(os.environ, DEVKITPRO=str(sdk), DEVKITA64=str(sdk / "devkitA64"))
env["PATH"] = f"{sdk}/devkitA64/bin:{sdk}/tools/bin:" + env["PATH"]
dest.mkdir(parents=True, exist_ok=True)

try:
    cmake_source.write_text(cmake_text)
    engine_source.write_text(engine_text)
    dynarec_source.write_text(dynarec_text)
    syscall_source.write_text(syscall_text)
    vulkan_source.write_text(vulkan_text)
    runtime_source.write_text(runtime_text)

    # A clean build directory prevents stale objects compiled with SAVE_MEM.
    if build.exists():
        resolved_build = build.resolve()
        if resolved_build.parent != root.resolve() or resolved_build.name != "runtime-perf8-block-profile":
            raise RuntimeError("Refusing to clear unexpected build path")
        shutil.rmtree(resolved_build)
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
        raise RuntimeError("PERF8 must use final -O1 and must not define SAVE_MEM")
    subprocess.run(
        ["cmake", "--build", str(build), "--target", "wine-nx-runtime", "-j4"],
        env=env,
        check=True,
    )
    # Verify references in the compiled object, not merely strings in the NRO.
    disassembly = subprocess.check_output([
        str(sdk / "devkitA64/bin/aarch64-none-elf-objdump"), "-dr",
        str(build / "CMakeFiles/wine-nx-runtime.dir/source/wow64_box64_dynarec.c.obj"),
    ], text=True)
    selector = disassembly.split("<GetCurEnvByAddr>:", 1)[1].split("Disassembly of section", 1)[0]
    if "wine_nx_vk_successful_presents" not in selector and "pes13_perf8_select_env" not in selector:
        raise RuntimeError("Compiled translator does not reference the PERF8 policy trigger")
    with tempfile.TemporaryDirectory(prefix="pes13-perf8-nacp-", dir=root) as tmp:
        nacp = Path(tmp) / "perf8.nacp"
        subprocess.run([
            str(sdk / "tools/bin/nacptool"), "--create",
            "PES13-NX PERF8", "PES13-NX", "0.2.0", str(nacp),
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

(dest / "perf8-turbo.txt").write_text("1\n")

# Disable DXVK's CPU-side limiter. FIFO presentation still provides the
# display refresh ceiling, while the limiter warning and its pacing work go
# away. DXVK loads this file from the executable's working directory.
(dest / "drive_c/PES13/dxvk.conf").write_text(
    "# PES13-NX: let the Vulkan FIFO own the 60 Hz ceiling.\n"
    "d3d9.maxFrameRate = -1\n"
)

archive = project / "dist/pes13-perf8-overlay.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
    for path in sorted(dest.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(project / "dist/perf8"))
    zf.write(project / "docs/PERF8.md", "PERF8.md")
with zipfile.ZipFile(archive) as zf:
    assert zf.testzip() is None

nro_blob = (dest / "pes13-nx.nro").read_bytes()
assert nro_blob[16:20] == b"NRO0"
assert b"pes13-nx-0.2.0-perf8-block-profile" in nro_blob
assert b"DXVK_SHADER_CACHE_PATH=C:" in nro_blob
assert b"PERF8 block profile active" in nro_blob
assert b"host_present_ms_per_call" in nro_blob
from nro_assets import inspect_nro
inspect_nro(nro_blob, (project / "assets/icon.jpg").read_bytes(), expected_title="PES13-NX PERF8")
print(json.dumps({
    "nro_sha256": hashlib.sha256(nro_blob).hexdigest(),
    "zip": str(archive),
    "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "perf3_compat_profile_unchanged": True,
    "perf3_ntdll_unchanged": True,
    "save_mem": False,
    "hot_diagnostic_atomics": False,
    "compatible_until_successful_present": True,
    "unconditional_mutex_lock_restored": True,
    "post_init_game_profile": "BIGBLOCK=1 per block; other settings Compatible",
    "dxvk_builtin_limiter": False,
    "box64_final_optimization": "-O1",
    "hardware_tested": False,
}, indent=2))
