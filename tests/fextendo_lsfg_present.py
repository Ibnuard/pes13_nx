#!/usr/bin/env python3
"""Fault-inject the exact production present method with a modeled VI driver."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def check(vulkan_include):
    source = (ROOT/'src/runtime/fextendo_lsfg.cpp').read_text()
    start = source.index('    VkResult present(const VkPresentInfoKHR& info)')
    brace = source.index('{', start)
    depth=1; end=brace+1
    while depth:
        if source[end]=='{':depth+=1
        elif source[end]=='}':depth-=1
        end+=1
    method=source[start:end]
    tail_start=source.index('    try {\n        *result = state->presentation->present(*info);')
    tail=source[tail_start:source.index('\n}',tail_start)]
    error_start=source.index('    if (state->error != VK_SUCCESS)')
    error_end=source.index('    ++state->calls;',error_start)
    sticky=source[error_start:error_end]
    harness=r'''
#include <vulkan/vulkan.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
#include <cstdio>
template<class T> T handle(uintptr_t v) { if constexpr(std::is_pointer_v<T>) return reinterpret_cast<T>(v); else return static_cast<T>(v); }
static std::vector<std::string> events;
static VkResult acquire_result=VK_SUCCESS, generated_result=VK_SUCCESS, original_result=VK_SUCCESS;
static bool fail_submit=false, fail_wait=false;
struct Driver {
 VkResult AcquireNextImageKHR(VkDevice,VkSwapchainKHR,uint64_t,VkSemaphore,VkFence,uint32_t* index) {
  events.push_back("acquire"); if(acquire_result==VK_SUCCESS||acquire_result==VK_SUBOPTIMAL_KHR)*index=1; return acquire_result;
 }
};
struct Vk { Driver driver; Driver& df(){return driver;} VkDevice dev(){return handle<VkDevice>(1);} };
struct Fence { VkFence handle(){return ::handle<VkFence>(20);} };
struct Semaphore { VkSemaphore handle(){return ::handle<VkSemaphore>(30);} };
struct Command {
 const char* name;
 void begin(Vk&){} void memoryBarrier(Vk&){} void end(Vk&){}
 void submit(Vk&,std::vector<VkSemaphore> waits,VkSemaphore,uint64_t,std::vector<VkSemaphore> signals,VkSemaphore,uint64_t,VkFence){
  assert(waits.size()==1&&signals.size()==1); events.push_back(std::string("submit-")+name); if(fail_submit)throw std::runtime_error("submit failed");
 }
};
struct Slot {
 Command frame{"frame"},restore{"restore"};Fence frame_done,restore_done;Semaphore acquired;bool frame_pending{},restore_pending{};
 void wait(Vk&){if(fail_wait)throw std::runtime_error("fence timed out");}
};
struct Backend {
 VkImage sourceImage(int,size_t n){return handle<VkImage>(100+n);} VkImage destinationImage(int,int){return handle<VkImage>(200);}
 void recordFrame(int,Command&){}
};
struct Presentation {
 Vk vk;VkSwapchainKHR swapchain=handle<VkSwapchainKHR>(50);int context{};
 std::vector<VkImage> images{handle<VkImage>(60),handle<VkImage>(61)};
 std::vector<Slot> slots=std::vector<Slot>(3);std::vector<Semaphore> presented=std::vector<Semaphore>(2);
 std::unique_ptr<Backend> backend=std::make_unique<Backend>();uint64_t frame_index{};unsigned warmup{2};
 void capture(Command&,VkImage,VkImage,bool){} void output(Command&,VkImage,VkImage,VkImageLayout,VkAccessFlags){}
 VkResult show(const VkPresentInfoKHR&,uint32_t index,VkSemaphore,bool generated){
  if(generated){assert(index==0);events.push_back("generated");return generated_result;}
  assert(index==(warmup||frame_index<=2?0:1));events.push_back("original");return original_result;
 }
__METHOD__
};
struct State { std::unique_ptr<Presentation> presentation=std::make_unique<Presentation>();VkResult error=VK_SUCCESS;uint64_t calls=1; };
void trace(const char*){} void report_stats(const State*){}
int invoke(State* state,const VkPresentInfoKHR* info,VkResult* result) {
__STICKY__
__TAIL__
}
void reset(){events.clear();acquire_result=generated_result=original_result=VK_SUCCESS;fail_submit=fail_wait=false;}
int main(){
 VkSemaphore wait=handle<VkSemaphore>(3);VkSwapchainKHR swap=handle<VkSwapchainKHR>(50);uint32_t index=0;VkResult result=VK_SUCCESS,per_result=VK_SUCCESS;
 VkPresentInfoKHR info{VK_STRUCTURE_TYPE_PRESENT_INFO_KHR};info.waitSemaphoreCount=1;info.pWaitSemaphores=&wait;info.swapchainCount=1;info.pSwapchains=&swap;info.pImageIndices=&index;info.pResults=&per_result;
 State state;
 for(int i=0;i<2;++i){reset();assert(invoke(&state,&info,&result)==1&&result==VK_SUCCESS);assert((events==std::vector<std::string>{"submit-frame","original"}));}
 reset();assert(invoke(&state,&info,&result)==1&&result==VK_SUCCESS);assert((events==std::vector<std::string>{"submit-frame","generated","acquire","submit-restore","original"}));
 for(auto error:{VK_TIMEOUT,VK_NOT_READY,VK_ERROR_DEVICE_LOST,VK_ERROR_OUT_OF_DATE_KHR,VK_ERROR_SURFACE_LOST_KHR}){
  reset();State test;test.presentation->warmup=0;test.presentation->frame_index=2;acquire_result=error;
  assert(invoke(&test,&info,&result)==1);assert(result==(error<0?error:VK_ERROR_DEVICE_LOST));assert(per_result==result);assert(test.error==result);
  assert((events==std::vector<std::string>{"submit-frame","generated","acquire"}));events.clear();assert(invoke(&test,&info,&result)==1&&events.empty());
 }
 for(int stage=0;stage<2;++stage){
  reset();State test;test.presentation->warmup=0;test.presentation->frame_index=2;fail_wait=stage==0;fail_submit=stage==1;
  assert(invoke(&test,&info,&result)==1&&result==VK_ERROR_DEVICE_LOST&&test.error==VK_ERROR_DEVICE_LOST);
  events.clear();assert(invoke(&test,&info,&result)==1&&events.empty());
 }
 reset();State sub;sub.presentation->warmup=0;sub.presentation->frame_index=2;acquire_result=VK_SUBOPTIMAL_KHR;
 assert(invoke(&sub,&info,&result)==1&&result==VK_SUBOPTIMAL_KHR&&sub.error==VK_SUCCESS);
 reset();State bad;bad.presentation->warmup=0;bad.presentation->frame_index=2;generated_result=VK_ERROR_OUT_OF_DATE_KHR;
 assert(invoke(&bad,&info,&result)==1&&result==VK_ERROR_OUT_OF_DATE_KHR&&events.back()=="generated");
 puts("production present method: warmup, VI ordering, generated/original propagation, acquire timeout/not-ready, pre/post-submit exceptions and sticky-error replay passed");
}
'''
    harness=harness.replace('__METHOD__',method).replace('__STICKY__',sticky).replace('__TAIL__',tail)
    with tempfile.TemporaryDirectory(prefix='fextendo-lsfg-present-') as directory:
        temp=Path(directory);cpp=temp/'test.cpp';exe=temp/'test';cpp.write_text(harness)
        subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(vulkan_include),str(cpp),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)],check=True,text=True,capture_output=True)
        return result.stdout.strip()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--vulkan-include',type=Path,default=Path.home()/'.cache/pes13-nx-macos/mesa-switch/include');args=parser.parse_args();print(check(args.vulkan_include))
