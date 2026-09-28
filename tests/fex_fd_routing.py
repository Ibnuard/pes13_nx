"""Execute the linked Horizon descriptor queues with modeled pthread/FD services.

The old native init-thread handler deterministically adopts another thread's
descriptor when sends interleave.  The fixed queue must match the descriptor
named by the request, while preserving outbound FIFO behavior.  Scheduling,
allocation, dup and pthread services are modeled; queue/handler ARM64 is real.
"""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import struct

from fex_reservations import Model as NativeModel, arm, reg


class QueueModel(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.locks = set()
        self.allocations = set()
        self.next_allocation = self.data + 0x2000
        self.next_fd = 1000
        self.duplicates = {}
        self.closed = []
        self.signals = []
        self.waits = []
        self.wait_injections = []
        self.take_keys = []
        self.stop_after_takes = 0
        self.intercepted = False
        self.replies = []
        self.wire_request = None
        self.c2s = self.symbols['horizon_client_to_server_fds']
        self.s2c = self.symbols['horizon_server_to_client_fds']
        self.writer_addresses = {a for n, a in self.symbols.items()
                                 if n.startswith('horizon_server_write_reply')}

    def allocate(self, size):
        address = self.next_allocation
        self.next_allocation += (size + 15) & ~15
        assert self.next_allocation < self.data + 0xf000
        self.vm.mem_write(address, bytes(size))
        self.allocations.add(address)
        return address

    def entries(self, queue):
        """The native ABI has 16-byte mutex, 16-byte condvar, head and tail."""
        result = []
        node = self.uq(queue + 32)
        seen = set()
        while node:
            assert node not in seen, 'Descriptor queue cycle'
            seen.add(node)
            fd, key, following = struct.unpack('<IIQ', self.vm.mem_read(node, 16))
            result.append((node, fd, key))
            node = following
        assert self.uq(queue + 40) == (result[-1][0] if result else 0), 'Stale queue tail'
        return result

    def scheduler_send(self, fd):
        """Effect of a different client send while cond-wait releases its lock.

        This is the explicitly modeled scheduler boundary. Normal enqueue tests
        run horizon_server_send_fd itself, including its allocation and wakeup.
        """
        duplicate = self.next_fd
        self.next_fd += 1
        self.duplicates[duplicate] = fd
        node = self.allocate(16)
        self.vm.mem_write(node, struct.pack('<IIQ', duplicate, fd, 0))
        tail = self.uq(self.c2s + 40)
        self.q(tail + 8 if tail else self.c2s + 32, node)
        self.q(self.c2s + 40, node)

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == s.get('horizon_server_take_client_fd'):
            self.take_keys.append(vm.reg_read(reg(0)) & 0xffffffff)
            if self.stop_after_takes and len(self.take_keys) >= self.stop_after_takes:
                self.intercepted = True
                vm.emu_stop()
        if pc == s.get('pthread_mutex_lock'):
            address = vm.reg_read(reg(0))
            assert address not in self.locks, 'Recursive queue/object lock'
            self.locks.add(address)
            self.ret()
        elif pc == s.get('pthread_mutex_unlock'):
            address = vm.reg_read(reg(0))
            assert address in self.locks, 'Unlock without lock'
            self.locks.remove(address)
            self.ret()
        elif pc in {s.get('pthread_cond_signal'), s.get('pthread_cond_broadcast')}:
            cond = vm.reg_read(reg(0))
            assert cond - 16 in self.locks
            self.signals.append(('broadcast' if pc == s.get('pthread_cond_broadcast') else 'signal', cond))
            self.ret()
        elif pc == s.get('pthread_cond_wait'):
            cond, mutex = [vm.reg_read(reg(i)) for i in range(2)]
            assert mutex in self.locks and cond == mutex + 16
            self.waits.append((cond, mutex))
            assert self.wait_injections, 'Unexpected unbounded descriptor wait'
            injection = self.wait_injections.pop(0)
            self.locks.remove(mutex)
            if injection is not None:
                self.scheduler_send(injection)
            self.locks.add(mutex)
            self.ret()
        elif pc == s.get('malloc'):
            assert not self.locks, 'Allocation under queue lock'
            self.ret(self.allocate(vm.reg_read(reg(0))))
        elif pc == s.get('free'):
            address = vm.reg_read(reg(0))
            assert not self.locks and address in self.allocations
            self.allocations.remove(address)
            self.ret()
        elif pc == s.get('dup'):
            source = vm.reg_read(reg(0)) & 0xffffffff
            duplicate = self.next_fd
            self.next_fd += 1
            self.duplicates[duplicate] = source
            self.ret(duplicate)
        elif pc == s.get('close'):
            self.closed.append(vm.reg_read(reg(0)) & 0xffffffff)
            self.ret()
        elif pc == s.get('getpid'):
            self.ret(123)
        elif pc in {s.get('__emutls_get_address'), s.get('__aarch64_read_tp')}:
            self.ret(self.data + 0x1000)
        elif pc in {s.get('wine_nx_thread_register'), s.get('svcSetThreadPriority')}:
            self.ret()
        elif pc == s.get('read') and self.wire_request is not None:
            _, pointer, length = [vm.reg_read(reg(i)) for i in range(3)]
            assert length == 64 and not self.locks
            vm.mem_write(pointer, self.wire_request.ljust(64, b'\0'))
            self.wire_request = None
            self.ret(length)
        elif pc == s.get('write'):
            assert not self.locks
            fd, pointer, length = [vm.reg_read(reg(i)) for i in range(3)]
            assert length == 64
            self.replies.append((fd, bytes(vm.mem_read(pointer, length))))
            self.ret(length)
        else:
            super().hook(vm, pc, size, user)

    def call(self, name, *args):
        self.returned = self.intercepted = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate(args):
            self.vm.reg_write(reg(i), value & 0xffffffffffffffff)
        address = self.symbols[name]
        self.vm.emu_start(address, 0, count=100000)
        assert self.returned or self.intercepted, f'{name} did not return'
        if self.returned:
            assert not self.locks
        return self.vm.reg_read(reg(0)) & 0xffffffff

    def send(self, source):
        prior = self.next_fd
        self.call('horizon_server_send_fd', source)
        assert self.next_fd == prior + 1
        self.entries(self.c2s)
        return prior

    def take(self, expected):
        result = self.call('horizon_server_take_client_fd', expected)
        self.entries(self.c2s)
        return result

    def init_thread(self, reply_fd, wait_fd):
        connection, request = self.data + 0x500, self.data + 0x600
        self.vm.mem_write(connection, bytes(80))
        self.vm.mem_write(connection, struct.pack('<5i', 77, -1, -1, 123, 40))
        # header(req,size,replysize), unix_tid, reply_fd, wait_fd, teb, entry.
        self.vm.mem_write(request, struct.pack('<6I2Q', 6, 0, 0, 40,
                                             reply_fd, wait_fd, 0x30000000, 0x40000000))
        self.call('horizon_server_handle_init_thread', connection, request)
        return struct.unpack('<2I', self.vm.mem_read(connection + 4, 8))


def old_reproduction(path):
    model = QueueModel(path)
    # Parent starts another worker between child's two pipe sends.
    child_reply = model.send(101)
    parent_request = model.send(202)
    child_wait = model.send(103)
    adopted = model.init_thread(101, 103)
    assert adopted == (child_reply, parent_request)
    assert adopted != (child_reply, child_wait)
    # A later new_thread would take the remaining child wait pipe as its request.
    remaining = model.entries(model.c2s)
    assert len(remaining) == 1 and remaining[0][1] == child_wait
    return {'reproduced': True, 'requested_original_fds': [101, 103],
            'adopted_original_fds': [model.duplicates[fd] for fd in adopted],
            'remaining_original_fd': model.duplicates[remaining[0][1]]}


def run_checks(path):
    scenarios = 0
    # All send-order permutations, including a descriptor for an unrelated
    # request ahead of, between, and after the two child init descriptors.
    for order in itertools.permutations((101, 202, 103)):
        model = QueueModel(path)
        duplicates = {fd: model.send(fd) for fd in order}
        assert model.init_thread(101, 103) == (duplicates[101], duplicates[103])
        assert model.take(202) == duplicates[202]
        assert model.entries(model.c2s) == [] and not model.allocations
        assert all(kind == 'broadcast' for kind, _ in model.signals)
        scenarios += 1
    # Unlink middle, tail, head, last; append after emptied queue; repeated
    # original descriptor keys are consumed in their own enqueue order.
    model = QueueModel(path)
    sent = [(fd, model.send(fd)) for fd in (10, 20, 10, 30, 40)]
    for source, duplicate in (sent[1], sent[4], sent[0], sent[3], sent[2]):
        assert model.take(source) == duplicate
        scenarios += 1
    again = model.send(10)
    assert model.take(10) == again and not model.entries(model.c2s)
    assert not model.allocations
    scenarios += 1
    # Condvar wakeups do not imply that the requested key exists. There is a
    # spurious wake, then another request's descriptor, then the desired one.
    model = QueueModel(path)
    model.wait_injections = [None, 55, 66]
    result = model.take(66)
    assert model.duplicates[result] == 66 and len(model.waits) == 3
    assert model.duplicates[model.take(55)] == 55
    assert not model.allocations and not model.entries(model.c2s)
    scenarios += 1
    # Outbound queue retains FIFO and its Windows handle tags, including zero.
    model = QueueModel(path)
    push = 'horizon_fd_queue_push_dup'
    assert push in model.symbols, 'Outbound queue enqueue entry unavailable'
    for source, handle in ((81, 0x124), (82, 0), (83, 0x128)):
        model.call(push, model.s2c, source, handle)
    result_ptr = model.data + 0x100
    for source, handle in ((81, 0x124), (82, 0), (83, 0x128)):
        fd = model.call('horizon_server_receive_fd', result_ptr)
        assert model.duplicates[fd] == source
        assert struct.unpack('<I', model.vm.mem_read(result_ptr, 4))[0] == handle
        scenarios += 1
    assert not model.entries(model.s2c) and not model.allocations
    assert all(kind == 'signal' for kind, _ in model.signals)
    # The other startup request handlers must pass the original fd fields,
    # not a stack pointer or the existing connection's descriptor. Stop at
    # their handoff boundaries, before unrelated object/thread allocation.
    for name, request, expected in (
        ('horizon_server_handle_init_first_thread',
         struct.pack('<8I', 5, 0, 0, 123, 4, 0, 301, 302), [301, 302]),
        ('horizon_server_handle_new_thread',
         struct.pack('<7I', 2, 0, 0, 0xffffffff, 0x1fffff, 1, 401), [401]),
    ):
        model = QueueModel(path)
        for source in expected:
            model.send(source)
        connection, message = model.data + 0x500, model.data + 0x600
        model.vm.mem_write(connection, bytes(80))
        model.vm.mem_write(message, request)
        model.stop_after_takes = len(expected)
        if name in model.symbols:
            model.call(name, connection, message)
        else:
            # GCC can inline the first-thread handler into the server loop.
            # Feed that real loop a wire request and stop at the same handoff.
            assert name == 'horizon_server_handle_init_first_thread'
            model.wire_request = request
            model.call('horizon_server_thread', connection)
        assert model.intercepted and model.take_keys == expected
        assert not model.locks
        scenarios += 1
    # Unsupported file-handle conversion still rejects the request, but its
    # descriptor must be discarded. Otherwise original fd reuse can later
    # select that stale duplicate even with identity-based routing.
    model = QueueModel(path)
    unrelated = model.send(501)
    rejected = model.send(502)
    connection, message = model.data + 0x500, model.data + 0x600
    model.vm.mem_write(connection, bytes(80))
    model.vm.mem_write(connection + 4, struct.pack('<I', 900))
    model.vm.mem_write(message, struct.pack('<6I', 0, 0, 0, 0x10000000, 0, 502))
    model.call('horizon_server_discard_alloc_file_fd', connection, message)
    assert model.closed == [rejected]
    assert len(model.replies) == 1 and model.replies[0][0] == 900
    assert struct.unpack('<I', model.replies[0][1][:4])[0] == 0xc0000002
    assert model.take(501) == unrelated
    reused = model.send(502)
    assert model.take(502) == reused and reused != rejected
    assert not model.allocations and not model.entries(model.c2s)
    scenarios += 1
    return scenarios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before = old_reproduction(args.before)
    scenarios = run_checks(args.elf)
    report = {'passed': True,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'before_native_elf_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'before': before, 'scenarios': scenarios,
              'checks': ['Actual old init_thread adopts a different thread request pipe after interleaved sends',
                         'Actual fixed ARM64 queue matches all six interleaved send orders',
                         'Head/middle/tail unlink, empty/reuse and duplicate-key FIFO preserve ownership',
                         'Spurious and unrelated wakeups recheck the requested descriptor',
                         'Client sends broadcast to keyed waiters; outbound sends retain signal and FIFO',
                         'Actual first-thread/new-thread handlers pass their request fd fields',
                         'Unsupported alloc_file_handle closes only its own duplicate and preserves rejection status; original fd reuse stays safe'],
              'scope': 'Linked ARM64 descriptor queues and init_thread handler; malloc/dup/pthread services and scheduler boundaries modeled. Switch boot still requires device testing.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
