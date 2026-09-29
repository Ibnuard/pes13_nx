#!/usr/bin/env python3
"""Check native bridge wiring and real resource parser without claiming GPU validation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_dll(ids, invalid=None):
    """Minimal PE32+ resource tree, no executable code or third-party shaders."""
    n = len(ids)
    tables = 40 + 16 + n * 8
    entries = tables + n * 24
    payload = entries + n * 16
    resources = bytearray(payload + n * 20)
    struct.pack_into('<HH', resources, 12, 0, 3)
    for i, kind in enumerate((3, 10, 16)):
        struct.pack_into('<II', resources, 16 + 8 * i, kind, 0x80000000 | 40)
    struct.pack_into('<HH', resources, 52, 0, n)
    for i, resource in enumerate(ids):
        language, entry, body = tables + 24*i, entries + 16*i, payload + 20*i
        struct.pack_into('<II', resources, 56 + 8*i, resource, 0x80000000 | language)
        struct.pack_into('<HH', resources, language + 12, 0, 1)
        struct.pack_into('<II', resources, language + 16, 1033, entry)
        struct.pack_into('<IIII', resources, entry, 0x1000 + body, 20, 0, 0)
        struct.pack_into('<IIIII', resources, body, 0x07230203 if resource != invalid else 0x43425844,
                         0x10000, 0, 1, 0)
    image = bytearray(512)
    struct.pack_into('<H', image, 0, 0x5a4d)
    struct.pack_into('<I', image, 60, 128)
    struct.pack_into('<IHH', image, 128, 0x4550, 0x8664, 1)
    struct.pack_into('<H', image, 148, 240)
    struct.pack_into('<H', image, 152, 0x20b)
    struct.pack_into('<II', image, 280, 0x1000, len(resources))
    struct.pack_into('<IIII', image, 400, len(resources), 0x1000, len(resources), 512)
    return image + resources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--backend-source', type=Path, default=ROOT/'local/fex3/lsfg-build/source')
    parser.add_argument('--backend-work', type=Path, default=ROOT/'local/fex3/lsfg-build')
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--dll', type=Path, default=ROOT/'TEST RESULT/Lossless.dll')
    parser.add_argument('--vulkan-include', type=Path, default=Path.home()/'.cache/pes13-nx-macos/mesa-switch/include')
    parser.add_argument('--allow-unlinked', action='store_true', help='Only for early bring-up; release checks require final ELF')
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    source = args.backend_source.resolve()
    registry = (source/'lsfg-vk-backend/src/extraction/shader_registry.cpp').read_text()
    offsets = {name:int(value) for name,value in re.findall(r'const size_t (BASE_OFFSET|OFFSET_PERF|OFFSET_FP32) = (\d+);', registry)}
    ids = sorted(set(map(int, re.findall(r'SHADER\((\d+),', registry))))
    generate = int(re.search(r'generate_data = getShaderSource\((\d+),', registry)[1])
    base = offsets['BASE_OFFSET'] + offsets['OFFSET_FP32']
    required = sorted({base+generate} | {base+i+perf*offsets['OFFSET_PERF'] for i in ids for perf in range(2)})
    assert len(required) == 45 and ids == list(range(257,279))
    from fextendo_lsfg_present import check as check_present
    checks = [check_present(args.vulkan_include)]
    with tempfile.TemporaryDirectory(prefix='fextendo-lsfg-') as directory:
        temp = Path(directory)
        main_cpp = temp/'main.cpp'
        main_cpp.write_text('''#include <vulkan/vulkan.h>
#include "fextendo_lsfg_config.h"
#include <cstdio>
extern "C" void wine_nx_runtime_trace(const char* text) { std::puts(text); }
extern "C" VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vkGetInstanceProcAddr(VkInstance, const char*) { return nullptr; }
int main() { int result=wine_nx_lsfg_available(); std::printf("AVAILABLE=%d REASON=%s\\n",result,wine_nx_lsfg_unavailable_reason()); wine_nx_lsfg_configure(1,1,1); return result; }
''')
        include = ['-I'+str(args.backend_work/'install/include'), '-I'+str(args.vulkan_include), '-I'+str(ROOT/'src/runtime')]
        glue = temp/'glue.o'; exe=temp/'availability'
        subprocess.run(['c++','-std=c++20','-ffunction-sections','-fdata-sections',*include,'-c',str(ROOT/'src/runtime/fextendo_lsfg.cpp'),'-o',str(glue)],check=True)
        subprocess.run(['c++','-std=c++20','-Wl,-dead_strip',*include,str(main_cpp),str(glue),str(source/'lsfg-vk-backend/src/extraction/dll_reader.cpp'),str(source/'lsfg-vk-common/src/helpers/errors.cpp'),'-o',str(exe)],check=True)
        target = temp/'sdmc:/switch/pes13-fex/lsfg/Lossless.dll'
        target.parent.mkdir(parents=True)
        def run(expected):
            result = subprocess.run([str(exe)],cwd=temp,text=True,capture_output=True)
            assert result.returncode == expected, result.stdout + result.stderr
            return result.stdout
        assert 'Copy a compatible' in run(0)
        target.write_bytes(fake_dll(required))
        assert 'compatible shader payload' in run(1)
        target.write_bytes(fake_dll(required[:-1]))
        assert 'lacks compatible SPIR-V' in run(0)
        target.write_bytes(fake_dll(required, required[0]))
        assert 'lacks compatible SPIR-V' in run(0)
        target.write_bytes(b'MZ')
        assert 'lacks compatible SPIR-V' in run(0)
        checks.append('Actual bridge + pinned PE reader: missing file, complete synthetic resource set, missing required shader, wrong shader magic and truncated PE; validation does not call a GPU API.')
        shutil.copy2(args.dll, target)
        supplied = subprocess.run([str(exe)],cwd=temp,text=True,capture_output=True)
        assert supplied.returncode == 0 and 'lacks compatible SPIR-V' in supplied.stdout
        checks.append('Supplied Lossless Scaling 3.2.1.0 DLL rejected before feature negotiation or swapchain modification; no Windows code loaded.')
    native = (args.source/'dlls/win32u/vulkan.c').read_text()
    cmake = (args.source/'wine-nx-probe/CMakeLists.txt').read_text()
    wired = 'wine_nx_lsfg_prepare_swapchain' in native
    if wired:
        assert native.count('++swapchain->lsfg_acquires;') == native.count('--swapchain->lsfg_acquires;') == 2
        assert 'static pthread_mutex_t present_lock = PTHREAD_MUTEX_INITIALIZER;' in native
        assert 'static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;' not in native[native.index('static VkResult win32u_vkQueuePresentKHR'):]
        assert native.index('wine_nx_lsfg_prepare_swapchain') < native.index('device->p_vkCreateSwapchainKHR(')
        assert native.index('wine_nx_lsfg_destroy( swapchain->lsfg )') < native.index('device->p_vkDestroySwapchainKHR(',native.index('void win32u_vkDestroySwapchainKHR'))
        assert '!swapchain_from_handle( client_swapchains[0] )->lsfg_acquires' in native
        assert '-ffixed-x18' in cmake and 'PES13_LSFG_PREFIX' in cmake
        checks.append('Final Wine wiring: acquire markers share presentation mutex, prepare before create, LSFG destruction before host swapchain, and normal native fallback remain in place.')
    else:
        assert args.allow_unlinked, 'LSFG hooks missing from final native source'
    glue = (ROOT/'src/runtime/fextendo_lsfg.cpp').read_text()
    assert 'if (state->error != VK_SUCCESS)' in glue
    assert 'if (*result < VK_SUCCESS) state->error = *result;' in glue
    assert '*result = VK_ERROR_DEVICE_LOST;' in glue
    assert 'return acquired < VK_SUCCESS ? acquired : VK_ERROR_DEVICE_LOST;' in glue
    assert 'return 0;' not in glue[glue.index('    try {\n        *result = state->presentation->present'):]
    assert 'if (!generate || info->pNext || info->swapchainCount != 1' in glue
    assert 'presented[index].handle()' in glue and 'warmup{2}' in glue
    assert 'original_frames' in glue and 'generated_frames' in glue
    checks.append('Presentation source audit: unsupported extension chains and concurrent acquires bypass before consuming waits; post-submit failures stay errors; per-image semaphores, temporal warmup, separate original/generated counters retained.')
    elf = work/'runtime/reference/pes13-fex.elf'
    if elf.exists():
        nm = subprocess.check_output(['/opt/devkitpro/devkitA64/bin/aarch64-none-elf-nm',str(elf)],text=True)
        for name in ('wine_nx_lsfg_available','wine_nx_lsfg_configure','wine_nx_lsfg_present','wine_nx_lsfg_prepare_swapchain'):
            assert re.search(r'\bT '+name+r'$',nm,re.M), name
        checks.append('Final ARM64 ELF contains native LSFG availability, configuration, swapchain and presentation implementations.')
    else:
        assert args.allow_unlinked, 'Final ELF required'
    files=['src/runtime/fextendo_lsfg.cpp','src/runtime/fextendo_lsfg.h','src/runtime/fextendo_lsfg_config.h','tools/fextendo_lsfg_patches.py','tools/build-fextendo-lsfg.py','tests/fextendo_lsfg.py','tests/fextendo_lsfg_resources.cpp','tests/fextendo_lsfg_present.py']
    files += [str(p.relative_to(ROOT)) for p in sorted((ROOT/'third_party/lsfg-horizon').rglob('*')) if p.is_file()]
    result={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(elf) if elf.exists() else None,
            'native_hooks_verified':wired,'checks':checks,'source_hashes':{f:sha(ROOT/f) for f in files},
            'backend_library_sha256':sha(args.backend_work/'install/lib/liblsfg-vk.a'),
            'backend_manifest_sha256':sha(args.backend_work/'build-manifest.json'),
            'generated_nvk_shaders':len(list((args.backend_work/'fextendo-build/generated').glob('*.h'))),
            'dll':{'sha256':sha(args.dll),'version':'3.2.1.0','compatible':False,'required_fp32_resource_ids':required,
                   'reason':'Provided DLL contains DXBC only; pinned backend requires SPIR-V resources.'}}
    (work/'lsfg-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
