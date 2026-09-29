int main(){
    unsetenv("FEXTENDO_TRACE");PES13FexJitTimingInit();assert(!ShortEnabled);
    uint64_t start=clock_ticks.load();clock_ticks+=19200*30;PES13FexJitEnd(1,start);assert(ShortSlots[1].window.count==0);
    setenv("FEXTENDO_TRACE","1",1);PES13FexJitTimingInit();assert(ShortEnabled);
    start=clock_ticks.load();clock_ticks+=19200*30;
    for(int i=0;i<6;i++)PES13FexJitEnd(1,start);
    const auto &w=ShortSlots[1].window;
    assert(w.count==6&&w.tid==4&&w.ticks==6*19200*30&&w.slow_count==4&&w.slow_dropped==2);
    test_teb.ClientId.UniqueThread=(void*)516;PES13FexJitEnd(1,start);assert(ShortDropped==1&&w.tid==4);
    test_teb.ClientId.UniqueThread=(void*)4;ShortSlots[1].busy.test_and_set();PES13FexJitEnd(1,start);ShortSlots[1].busy.clear();assert(ShortDropped==2);
    clock_ticks+=19200000*5;PES13FexJitReport();assert(!ShortSlots[1].window.count);
    unsigned slow=0,aggregate=0;for(const auto &m:messages){
        if(m.find("[FEX3-JIT-SLOW]")==0){slow++;assert(m.find("tid=4")!=std::string::npos&&m.find("wall_us=30000")!=std::string::npos);}
        if(m.find("[FEX3-JIT-THREAD]")==0){aggregate++;assert(m.find("calls=6")!=std::string::npos&&m.find("total_us=180000")!=std::string::npos);}
    }assert(slow==4&&aggregate==1);
    std::vector<std::thread> threads;
    for(int i=0;i<8;i++)threads.emplace_back([i]{test_teb.ClientId.UniqueThread=(void*)(uintptr_t)(4+i*4);for(int j=0;j<2000;j++)PES13FexJitEnd(1,clock_ticks.load()-19200);});
    for(auto &t:threads)t.join();for(unsigned i=1;i<=8;i++){assert(ShortSlots[i].window.count==2000);assert(ShortSlots[i].window.slow_count==0);}
    clock_ticks+=19200000*5;PES13FexJitReport();
    setenv("FEXTENDO_TRACE","0",1);PES13FexJitTimingInit();assert(!ShortEnabled);
    puts("PASS FEX per-thread compile attribution, exact ticks, OFF, bounded slow events, collisions and concurrent compiles");
}
