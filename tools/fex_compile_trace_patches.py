"""Attribute cold compiler stages and retained expensive guest block entries."""


def apply(read, replace, project):
    name='Source/Windows/WOW64/CMakeLists.txt'
    anchor='  "${PES13_HORIZON_DIR}/module_jit_timing.cpp"\n'
    replace(name,anchor,anchor+'  "${PES13_HORIZON_DIR}/module_compile_trace.cpp"\n')
    name='FEXCore/Source/Interface/Context/Context.h'
    old='GenerateIRResult GenerateIR(FEXCore::Core::InternalThreadState* Thread, uint64_t GuestRIP, bool ExtendedDebugInfo, uint64_t MaxInst);'
    replace(name,old,old[:-2]+', uint64_t* HorizonPhases = nullptr);')
    name='FEXCore/Source/Interface/Core/Core.cpp'
    anchor='#include "horizon_jit_timing.h"'
    replace(name,anchor,anchor+'\n#include "horizon_compile_trace.h"')
    old='ContextImpl::GenerateIR(FEXCore::Core::InternalThreadState* Thread, uint64_t GuestRIP, bool ExtendedDebugInfo, uint64_t MaxInst) {'
    replace(name,old,old.replace('uint64_t MaxInst)', 'uint64_t MaxInst, uint64_t* HorizonPhases)')+
            '\n  PES13FexCompilePhase HorizonFrontend{HorizonPhases, 2};')
    replace(name,'    Thread->FrontendDecoder->DecodeLoop(GuestCode);',
            '    { PES13FexCompilePhase HorizonDecode{HorizonPhases, 0};\n'
            '      Thread->FrontendDecoder->DecodeLoop(GuestCode); }')
    replace(name,'  Thread->PassManager->Run(IREmitter);',
            '  { PES13FexCompilePhase HorizonPasses{HorizonPhases, 1};\n'
            '    Thread->PassManager->Run(IREmitter); }')
    replace(name,'  PES13FexJitScope HorizonCompileTiming{1};',
            '  PES13FexJitScope HorizonCompileTiming{1};\n  PES13FexCompileTrace HorizonCompileTrace{GuestRIP};')
    replace(name,'    GenerateIR(Thread, GuestRIP, Config.GDBSymbols(), MaxInst);',
            '    GenerateIR(Thread, GuestRIP, Config.GDBSymbols(), MaxInst, HorizonCompileTrace.Phases());')
    replace(name,'      // Raced to compile, release the OpDispatcher IR.',
            '      HorizonCompileTrace.outcome = 2;\n      // Raced to compile, release the OpDispatcher IR.')
    old='  auto CompiledCode = Thread->CPUBackend->CompileCode(GuestRIP, Length, TotalInstructions == 1, &*IRView, DebugData.get(), TFSet);'
    replace(name,old,'''  auto CompiledCode = [&] {
    PES13FexCompilePhase HorizonBackend{HorizonCompileTrace.Phases(), 3};
    return Thread->CPUBackend->CompileCode(GuestRIP, Length, TotalInstructions == 1, &*IRView, DebugData.get(), TFSet);
  }();
  HorizonCompileTrace.outcome = CompiledCode.BlockBegin ? 1 : 0;
  HorizonCompileTrace.instructions = TotalInstructions;
  HorizonCompileTrace.host_bytes = CompiledCode.Size;''')
