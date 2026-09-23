"""Verify restored sources, unchanged game policy, and linked Vulkan timers."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

from nro_assets import inspect_nro
from perf44_patches import patch_vulkan, patch_thunks
from perf24_patches import adapt_vulkan
from perf17_patches import once

project = Path(__file__).resolve().parents[1]
work = project / 'local/perf44'
root = Path(os.environ.get('PES_BUILD_ROOT', '/home/blekjek/pes13-build'))
source = root / 'runtime-perf11-source'
build = root / 'runtime-perf44-event-pipeline'
old = root / 'runtime-perf42-startup-guard'
sha = lambda data: hashlib.sha256(data).hexdigest()
nm = '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm'
objdump = '/opt/devkitpro/devkitA64/bin/aarch64-none-elf-objdump'

assert json.loads((work / 'build-status.json').read_text()) == {
    'state': 'complete', 'restored': True}
for name, digest in json.loads((work / 'source-baseline.json').read_text()).items():
    assert sha((source / name).read_bytes()) == digest, name
assert (work / 'wow64_box64_unix.c').read_bytes() == (
    project / 'local/perf42/wow64_box64_unix.c').read_bytes()

for name in ('wine-nx-box64-core-dynarec.c',
             'wine-nx-box64-core-dynablock.c',
             'wine-nx-box64-core-dynarec_native.c'):
    assert (build / name).read_bytes() == (old / name).read_bytes(), name
emitters = sorted((work / 'generated').glob('*.c'))
assert len(emitters) == 14
for file in emitters:
    assert file.read_bytes() == (project / 'local/perf42/generated' / file.name).read_bytes()

baseline = work / 'source-baseline'
vulkan = (baseline / 'dlls/win32u/vulkan.c').read_text()
vulkan = once(vulkan, 'unsigned int wine_nx_vk_presents;',
    'unsigned int wine_nx_vk_presents;\n'
    'unsigned int wine_nx_vk_successful_presents, wine_nx_vk_host_present_calls;\n'
    'unsigned long long wine_nx_vk_host_present_ticks;\n'
    'extern unsigned long long wine_nx_perf8_tick(void);')
vulkan = once(vulkan,
    '    if (res == VK_SUCCESS && presents > 4 && presents % 1800) return;',
    '    if (count && (res == VK_SUCCESS || res == VK_SUBOPTIMAL_KHR))\n'
    '        __atomic_add_fetch(&wine_nx_vk_successful_presents, 1, __ATOMIC_RELEASE);\n'
    '    if (res == VK_SUCCESS && presents > 4 && presents % 1800) return;')
vulkan = once(vulkan,
    '    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );',
    '''#ifdef __SWITCH__
    {
        unsigned long long begin = wine_nx_perf8_tick();
        res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );
        __atomic_add_fetch(&wine_nx_vk_host_present_ticks, wine_nx_perf8_tick() - begin, __ATOMIC_RELAXED);
        __atomic_add_fetch(&wine_nx_vk_host_present_calls, 1, __ATOMIC_RELAXED);
    }
#else
    res = device->p_vkQueuePresentKHR( queue->host.queue, present_info );
#endif''')
assert (work / 'vulkan.c').read_text() == patch_vulkan(adapt_vulkan(vulkan), project)
assert (work / 'vulkan_thunks.c').read_text() == patch_thunks(
    (baseline / 'dlls/winevulkan/vulkan_thunks.c').read_text(), project)
assert (work / 'vulkan.c').read_text().count('PES44_TIME(') == 7
assert (work / 'vulkan_thunks.c').read_text().count('PES44_TIME(') == 8

elf = build / 'wine-nx-runtime.elf'
symbols = subprocess.check_output([nm, str(elf)], text=True)
assert ' wine_nx_perf44_span\n' in symbols
assert ' wine_nx_perf42_guard_enabled\n' in symbols
objects = [
    build / 'CMakeFiles/wine-win32u-real.dir' /
    'home/blekjek/pes13-build/runtime-perf11-source/dlls/win32u/vulkan.c.obj',
    build / 'CMakeFiles/wine-winevulkan-unix-real.dir' /
    'home/blekjek/pes13-build/runtime-perf11-source/dlls/winevulkan/vulkan_thunks.c.obj',
]
for obj in objects:
    assert ' U wine_nx_perf44_span\n' in subprocess.check_output(
        [nm, '-u', str(obj)], text=True), obj
disassembly = subprocess.check_output([objdump, '-d', str(elf)], text=True)
linked_span_calls = disassembly.count('<wine_nx_perf44_span>') - 1
assert linked_span_calls >= 8, linked_span_calls

nro = (work / 'payload/switch/pes13-nx/pes13-nx.nro').read_bytes()
assert b'pes13-nx-0.2.0-perf44-event-pipeline' in nro
assert b'[PIPE44]' in nro and b'[BOOT42]' in nro and b'[JIT37]' not in nro
assert sha(nro) == json.loads((work / 'build.json').read_text())['nro_sha256']
metadata = inspect_nro(nro, (project / 'assets/icon.jpg').read_bytes(),
                       expected_title='PES13-NX PERF44 PIPELINE')

report = json.loads((work / 'verification.json').read_text())
report.update(source_restored=True, same_game_emitters_as_perf42=True,
              same_unix_bootguard_as_perf42=True, nro_metadata=metadata,
              linked_span_calls=linked_span_calls,
              vulkan_objects_both_instrumented=True,
              changed_source_sha256={
                  str(file.relative_to(project)): sha(file.read_bytes())
                  for file in (
                      project / 'src/runtime/pes13_perf44_metrics.h',
                      project / 'src/runtime/pes13_perf44_runtime.h',
                      project / 'tools/perf44_patches.py',
                      project / 'tools/build-perf44.py',
                      project / 'tools/run-perf44-build.py',
                      project / 'tools/verify-perf44.py',
                  )})
(work / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
print('PERF44 source restoration, game-policy identity, linked timers PASS')
