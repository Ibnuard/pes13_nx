"""Exercise DXVK 2.7.1's actual limiter methods with host-side object stubs."""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

from fextendo_sarek_limiter import method

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/gplasync-2.7.1-trial'


def main():
    archive = WORK / 'dxvk-source-v2.7.1.tar.gz'
    if hashlib.sha256(archive.read_bytes()).hexdigest() != '9591f43bb5d7fe81213f784061c2a2180912b718665e410dd996b39eff92cb0b':
        raise ValueError('Pinned upstream source archive mismatch')
    paths = ['src/d3d9/d3d9_swapchain.cpp', 'src/util/util_fps_limiter.cpp']
    with tarfile.open(archive) as tar:
        prefix = tar.getnames()[0] + '/'
        source = [tar.extractfile(prefix + name).read().decode() for name in paths]
    update = method(source[0], 'void D3D9SwapChainEx::UpdateTargetFrameRate(uint32_t SyncInterval)')
    setter = method(source[1], 'void FpsLimiter::setTargetFrameRate(double frameRate, uint32_t maxLatency)')
    fixture = r'''
#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <mutex>
namespace dxvk {
using mutex = std::mutex;
enum class Tristate { Auto, False, True };
struct FpsLimiter {
  using TimerDuration = std::chrono::nanoseconds;
  using TimePoint = std::chrono::steady_clock::time_point;
  mutex m_mutex;
  bool m_envOverride=false, m_heuristicEnable=false;
  unsigned m_heuristicFrameCount=0, m_maxLatency=0;
  TimePoint m_heuristicFrameTime{};
  TimerDuration m_targetInterval{};
  void setTargetFrameRate(double, uint32_t);
};
struct Options { int maxFrameRate=-1; };
struct Parent { Options opts; Options* GetOptions() { return &opts; } };
struct Device {
  struct Config { Tristate latencySleep=Tristate::Auto; } cfg;
  const Config& config() { return cfg; }
};
struct Presenter {
  FpsLimiter limiter;
  void setFrameRateLimit(double rate, uint32_t latency) {
    limiter.setTargetFrameRate(rate, latency);
  }
};
struct Window { Presenter presenterObject; Presenter* presenter=&presenterObject; };
struct D3D9SwapChainEx {
  Parent parent; Device device; Window window;
  Parent* m_parent=&parent; Device* m_device=&device; Window* m_wctx=&window;
  bool m_monitor=false;
  double m_displayRefreshRate=60, m_targetFrameRate=0;
  uint32_t GetActualFrameLatency() { return 2; }
  void UpdateTargetFrameRate(uint32_t);
};
'''
    fixture += setter + '\n' + update + '\n}\n'
    fixture += r'''
int main() {
  dxvk::D3D9SwapChainEx s;
  auto& limiter=s.window.presenterObject.limiter;
  // A negative option must never become Sarek's accidental 1 FPS limit.
  for (bool monitor : {false, true}) {
    s.m_monitor=monitor;
    for (auto sleep : {dxvk::Tristate::Auto, dxvk::Tristate::True}) {
      s.device.cfg.latencySleep=sleep;
      for (unsigned sync : {0, 1, 2}) {
        s.UpdateTargetFrameRate(sync);
        assert(s.m_targetFrameRate==0 && limiter.m_targetInterval.count()==0);
      }
    }
  }
  s.parent.opts.maxFrameRate=60; s.UpdateTargetFrameRate(1);
  assert(limiter.m_targetInterval.count()==16666666);
  s.parent.opts.maxFrameRate=0; s.UpdateTargetFrameRate(2);
  assert(limiter.m_targetInterval.count()==-33333333);
  limiter.m_envOverride=true;
  s.parent.opts.maxFrameRate=-1; s.UpdateTargetFrameRate(1);
  assert(limiter.m_targetInterval.count()==-33333333);
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'limiter.cpp', Path(tmp) / 'limiter'
        cpp.write_text(fixture)
        subprocess.run(['clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra',
                        '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                        str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    report = {
        'passed': True, 'hardware_tested': False,
        'upstream_commit': 'c3dd74be6baec53786d4e064a572185b70347a17',
        'check': 'Actual upstream methods: -1 disables cap across sync/monitor/latency-sleep combinations; positive/auto caps and env override retained.',
        'source_sha256': {p: hashlib.sha256(s.encode()).hexdigest() for p, s in zip(paths, source)},
        'harness_sha256': hashlib.sha256(fixture.encode()).hexdigest(),
        'limits': 'Host ASan/UBSan test with object stubs; does not run the Windows DLL, GPU or Switch.',
    }
    (WORK / 'limiter-regression.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
