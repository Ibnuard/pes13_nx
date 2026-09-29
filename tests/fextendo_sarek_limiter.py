"""Reproduce Sarek's 1 FPS config regression using its pinned C++ methods."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/sarek-trial'


def method(text, signature):
    start = text.index(signature)
    begin = text.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def main():
    source = WORK / 'source/pythonlover02-dxvk-sarek-37f397e'
    release = WORK / 'release/dxvk-sarek-1.13.0'
    paths = ['src/util/util_fps_limiter.cpp', 'src/d3d9/d3d9_swapchain.cpp']
    texts = []
    for name in paths:
        data = (source / name).read_bytes()
        if data != (release / name).read_bytes():
            raise ValueError('Pinned source/release mismatch: ' + name)
        texts.append(data.decode())
    setter = method(texts[0], 'void FpsLimiter::setTargetFrameRate(double frameRate)')
    delay = method(texts[0], 'void FpsLimiter::delay(bool vsyncEnabled)')
    update = method(texts[1], 'void D3D9SwapChainEx::UpdateTargetFrameRate(UINT SyncInterval)')
    fixture = r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <mutex>
using UINT = unsigned;
namespace dxvk {
using mutex = std::mutex;
enum class FpsLimitMethod { Deviation, Timeline, Reactive };
class FpsLimiter {
public:
  using NtTimerDuration = std::chrono::duration<int64_t, std::ratio<1, 10000000>>;
  mutex m_mutex;
  bool m_envOverride=false, m_isSoftLimit=false, m_initialized=false;
  NtTimerDuration m_targetInterval{};
  FpsLimitMethod m_method=FpsLimitMethod::Deviation;
  unsigned init_calls=0, delay_calls=0;
  bool isEnabled() const { return m_targetInterval != NtTimerDuration::zero(); }
  void initialize() { ++init_calls; m_initialized=true; }
  void delayDeviation() { ++delay_calls; }
  void delayTimeline() { ++delay_calls; }
  void setTargetFrameRate(double);
  void delay(bool);
};
struct Options { int maxFrameRate=0; };
struct Parent { Options opts; Options* GetOptions() { return &opts; } };
struct Presenter {
  FpsLimiter limiter;
  void setFrameRateLimit(double rate) { limiter.setTargetFrameRate(rate); }
};
struct D3D9SwapChainEx {
  Parent parent; Presenter presenter;
  Parent* m_parent=&parent; Presenter* m_presenter=&presenter;
  double m_displayRefreshRate=60.0, m_targetFrameRate=0.0;
  void UpdateTargetFrameRate(UINT);
};
'''
    fixture += setter + '\n' + delay + '\n' + update + '\n}\n'
    fixture += r'''
int main() {
  using namespace dxvk;
  D3D9SwapChainEx s;
  auto& limiter=s.presenter.limiter;
  s.parent.opts.maxFrameRate=-1;
  s.UpdateTargetFrameRate(1);
  assert(limiter.m_targetInterval.count()==10000000); // exactly 1 second
  assert(limiter.isEnabled() && limiter.m_isSoftLimit);
  limiter.delay(true); assert(limiter.delay_calls==1);
  s.parent.opts.maxFrameRate=0;
  s.UpdateTargetFrameRate(1);
  assert(!limiter.isEnabled() && limiter.m_targetInterval.count()==0);
  limiter.delay(true); limiter.delay(false); assert(limiter.delay_calls==1);
  s.UpdateTargetFrameRate(0); assert(!limiter.isEnabled());
  s.UpdateTargetFrameRate(2); // preserve upstream half-refresh behaviour
  assert(limiter.m_targetInterval.count()==333333 && limiter.m_isSoftLimit);
  s.parent.opts.maxFrameRate=60;
  s.UpdateTargetFrameRate(1);
  assert(limiter.m_targetInterval.count()==166666 && !limiter.m_isSoftLimit);
  limiter.m_envOverride=true;
  s.parent.opts.maxFrameRate=0;
  s.UpdateTargetFrameRate(1);
  assert(limiter.m_targetInterval.count()==166666); // environment overrides config
  D3D9SwapChainEx fresh;
  fresh.UpdateTargetFrameRate(1);
  fresh.presenter.limiter.delay(true);
  assert(!fresh.presenter.limiter.isEnabled());
  assert(fresh.presenter.limiter.init_calls==0 && fresh.presenter.limiter.delay_calls==0);
  std::cout << "PASS: -1 produces 1-second cap; 0 disables limiter at interval 0/1; "
            << "interval 2, positive caps and env override retained\n";
}
'''
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / 'limiter.cpp', Path(tmp) / 'limiter'
        cpp.write_text(fixture)
        subprocess.run(['clang++', '-std=c++17', '-O1', '-g', '-Wall', '-Wextra',
                        '-Wno-unused-parameter', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', str(cpp), '-o', str(exe)], check=True)
        output = subprocess.check_output([str(exe)], text=True).strip()
    config = ROOT / 'config/fextendo/sarek-1.13.0.conf'
    values = dict(line.strip().split('=', 1) for line in config.read_text().splitlines()
                  if '=' in line and not line.lstrip().startswith('#'))
    values = {k.strip(): v.strip().strip('"') for k, v in values.items()}
    if values['d3d9.maxFrameRate'] != '0' or values['d3d9.presentInterval'] != '1':
        raise ValueError('Sarek config would reintroduce the limiter or change VSync')
    report = {'passed': True, 'hardware_tested': False, 'check': output,
              'upstream_commit': '37f397e142b977a343e920dbc4c7bf7ed2c63a81',
              'upstream_source_sha256': {n: hashlib.sha256((source/n).read_bytes()).hexdigest() for n in paths},
              'harness_sha256': hashlib.sha256(fixture.encode()).hexdigest(),
              'source_hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in (Path(__file__), config)},
              'limits': 'Extracted upstream methods on host with modeled initialization/delay hooks; does not execute Windows DLL, GPU or Switch.'}
    (WORK / 'limiter-regression.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
