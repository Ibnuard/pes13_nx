"""Execute production log sinks, the address-space gate and screen capture on ARM64.

Horizon memory queries and the display handoff are modeled. Unknown storage operations
fail. This does not emulate Switch VI presentation or boot the full game.
"""
import argparse,hashlib,json,struct
from pathlib import Path
from fextendo_silent import Model as QuietModel,reg

class Model(QuietModel):
    def __init__(self,path):
        super().__init__(path)
        self.info={12:0x200000,13:0xffe00000,3:0,6:3*1024**3,7:2*1024**3}
        self.query_error=None;self.notices=[];self.sd_started=0;self.queries=[]
        self.ui_joined=False;self.pad_started=False
    def hook(self,vm,pc,size,user):
        x=lambda i:vm.reg_read(reg(i))
        if pc==self.symbols.get('svcGetInfo'):
            kind=x(1);assert kind in self.info,kind
            self.queries.append(kind)
            if kind==self.query_error:self.ret(0xf601)
            else:vm.mem_write(x(0),struct.pack('<Q',self.info[kind]));self.ret(0)
        elif pc in {self.symbols.get('errorApplicationCreate'),self.symbols.get('errorApplicationShow')}:
            raise AssertionError('Rejection must not launch a nested system applet')
        elif pc==self.symbols.get('consoleInit'):self.ret(self.data+0x500)
        elif pc==self.symbols.get('printf'):
            self.notices.append((self.string(x(1)),self.string(x(2))));self.ret(0)
        elif pc in {self.symbols.get('padConfigureInput'),self.symbols.get('padInitializeWithMask'),self.symbols.get('consoleExit')}:
            self.ret(0)
        elif pc==self.symbols.get('appletMainLoop'):self.ret(0)
        elif pc in {self.symbols.get('pthread_mutex_lock'),self.symbols.get('pthread_mutex_unlock'),
                    self.symbols.get('pthread_mutex_trylock')}:self.ret(0)
        elif pc==self.symbols.get('pthread_join'):
            assert x(0)==101
            assert struct.unpack('<I',vm.mem_read(self.symbols['fx_ui_stop'],4))[0]==1
            # join returns only after launcher cleanup; VI itself is modeled.
            self.ui_joined=True;vm.mem_write(self.symbols['fx_ui_owned'],b'\0'*4);self.ret(0)
        elif pc==self.symbols.get('fx_pads_begin_game'):
            assert self.ui_joined;self.pad_started=True;self.ret(1)
        elif pc==self.symbols.get('wine_nx_compositor_enabled'):self.ret(0)
        elif pc==self.symbols.get('nwindowGetDefault'):
            assert self.ui_joined and self.pad_started;self.ret(self.data+0x500)
        elif pc==self.symbols.get('nwindowSetDimensions'):
            assert (x(0),x(1),x(2))==(self.data+0x500,1280,720);self.ret(0)
        elif pc==self.symbols.get('pthread_create'):
            raise AssertionError('Debug must not start an independent worker')
        else:
            if pc==self.symbols.get('wine_nx_sd_cache_install'):self.sd_started+=1
            super().hook(vm,pc,size,user)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('elf',type=Path)
    p.add_argument('--nro',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    m=Model(a.elf);m.check_stdio();assert m.sd_started==1 and not m.notices
    assert m.queries==[12,13,3,6]
    # A failed/unsupported launch must return before installing SD cache or
    # starting Wine, maintenance, renderer/preference writes and launcher UI.
    for label,values,error in (
        ('36-bit',{12:0x8000000,13:0xff8000000,3:0x180000000},None),
        ('32-bit with alias',{3:0x40000000},None),
        ('39-bit',{12:0x8000000,13:(1<<39)-0x8000000,3:1<<36},None),
        ('Unknown',{},13),('Unknown',{},3)):
        m.info={12:0x200000,13:0xffe00000,3:0,6:3*1024**3,7:2*1024**3};m.info.update(values)
        m.query_error=error;m.notices=[];m.sd_started=0;m.starting=True
        m.vm.mem_write(m.symbols['fx_startup_memory_read'],b'\0'*4)
        assert m.call('main',0,0)==0;m.starting=False
        assert not m.sd_started and len(m.notices)==1
        assert label in m.notices[0][0] and '32-bit no-alias' in m.notices[0][0]
        assert 'github.com/Ibnuard/pes13_nx/releases' in m.notices[0][1]
    m.query_error=None
    m.call('wine_nx_runtime_trace',1);m.call('horizon_trace',1)
    m.call('wine_nx_runtime_std_write',2,1,1048576);m.call('wine_nx_runtime_dump_std_streams')
    previous_queries=len(m.queries)
    m.call('fx_debug_file_tick');m.call('fx_crash_bootstrap');m.call('fx_crash_init',1)
    if 'horizon_dir_diag_begin' in m.symbols:
        assert not m.call('horizon_dir_diag_begin',0x1c34)
        m.call('horizon_dir_diag_stage',0,3);m.call('horizon_dir_diag_end',0,1)
        m.call('horizon_dir_diag_tick')
        assert bytes(m.vm.mem_read(m.symbols['horizon_dir_diag_slots'],16*24))==bytes(16*24)
    m.call('wine_nx_crash_exception',1,0xc0000005);m.call('wine_nx_crash_exit',7)
    m.call('wine_nx_crash_rust_allocation',1,1024,16,0,1)
    assert len(m.queries)==previous_queries
    assert m.call('fx_debug_file_prepare',1)==1 # invalid root pointer untouched in normal launch
    for key in ('profile','verbose','controller_trace','run_guest_tests','vulkan_probe','fex_hot_profile','fex_gap_probe','fex_game_timing'):
        assert m.config(key,1,1)==0,key
    for key in ('fex_fast_api','fex_diskcache','fex_auto_core3'):
        for value in (0,1):assert m.config(key,value,1-value)==value
    for tick in range(1,101):
        start=len(m.maintenance);m.call('fx_production_maintenance_tick',tick)
        assert m.maintenance[start:]==(['registry'] if tick%5==0 else [])+(['balance'] if tick%10==0 else [])
    m.vm.mem_write(m.data,b'loaddll\0');assert not m.call('wine_nx_launch_debug_flags',m.data)
    m.call('fx_launch_debug_begin',1);assert m.call('wine_nx_launch_debug_flags',m.data)==14
    message=b'[TEST] Wine loaded ntdll\n';m.vm.mem_write(m.data,message+b'\0')
    m.call('wine_nx_runtime_trace',m.data)
    m.call('wine_nx_runtime_std_write',2,m.data,len(message))
    m.call('horizon_trace',m.data)
    assert m.call('__wine_dbg_output',m.data)==len(message)
    # These are real ring bytes, not mocked capture callbacks.
    ring=bytes(m.vm.mem_read(m.symbols['fx_debug_ring'],64*109))
    assert ring.count(b'Wine loaded ntdll')==4,ring[:500]
    # Execute real GUI->game handoff. The launcher join precedes controller
    # service startup; no debug worker/layer can survive because none exists.
    for symbol,value in (('fx_ui_created',1),('fx_ui_owned',1),('fx_ui_thread',101)):
        m.vm.mem_write(m.symbols[symbol],struct.pack('<Q' if symbol=='fx_ui_thread' else '<I',value))
    assert m.call('wine_nx_gl_acquire_window')==m.data+0x500 and m.ui_joined and m.pad_started
    assert struct.unpack('<I',m.vm.mem_read(m.symbols['fx_debug_startup'],4))[0]==0
    ring=bytes(m.vm.mem_read(m.symbols['fx_debug_ring'],64*109));assert b'[HANDOFF]' in ring
    assert m.call('wine_nx_launch_debug_flags',m.data)==6
    m.vm.mem_write(m.data,b'late runtime error\n\0');m.call('wine_nx_runtime_trace',m.data)
    ring=bytes(m.vm.mem_read(m.symbols['fx_debug_ring'],64*109));assert b'late runtime error' in ring
    assert struct.unpack('<I',m.vm.mem_read(m.symbols['fx_debug_pending_size'],4))[0]>0
    m.call('fx_launch_debug_begin',0);assert not m.call('wine_nx_launch_debug_flags',1)
    m.call('fx_debug_file_tick')
    for name in ('fx_debug_console_main','fx_debug_console_start','fx_debug_health_poll','fx_diagnostics_tick',
                 'wine_nx_live_threads_snapshot','wine_nx_transition_begin','wine_nx_transition_end',
                 '__wrap_malloc'):
        assert name not in m.symbols,('diagnostic still linked',name)
    blob=a.nro.read_bytes()
    for path in (b'transition.log',b'launcher/diagnostics.txt',b'horizon-trace.log',
                 b'/stdout.txt',b'/stderr.txt',b'/stdin.txt',b'WINE_FTRACE_FILE'):
        assert path not in blob,('diagnostic path still linked',path)
    for token in (b'FEXTENDO_TRACE=0',b'DXVK_LOG_LEVEL=none',b'WINEDEBUG=-all',b'WINEDEBUG=err+all,warn+all',b'Show debug launch'):
        assert token in blob,token
    report={'passed':True,'hardware_tested':False,'native_elf_sha256':hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        'nro_sha256':hashlib.sha256(blob).hexdigest(),'checks':[
        'Real ARM64 startup validates kernel address/alias queries before SD setup',
        '32-bit no-alias proceeds; 36/39-bit, 32-bit with alias and failed queries stop with NSP instructions',
        'Quiet log callbacks and real null-device stdio execute with forbidden filesystem callees',
        'Debug producers queue real Wine/native/stdout messages without performing file I/O',
        'Real GUI handoff joins the launcher before game ownership; no independent debug worker exists',
        'After handoff the console is inactive while late errors still enter the file queue; quiet crash callbacks have no I/O',
        'Hostile profiling flags remain disabled; performance, registry persistence and CPU balancing remain intact',
        'ELF excludes overlay/health workers, thread sampling and the legacy transition logger'],
        'test_sources':{'tests/fextendo_production_binary.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
