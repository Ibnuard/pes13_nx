// Runs the real FEX DecodeLoop with synthetic instruction decoding and a
// bounded scratch buffer. This is a bounds/flow test, not an x86 ISA emulator.
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <limits>
#include <optional>
#include <set>
#include <vector>
#include "horizon_decode_set.h"
#define LOGMAN_THROW_A_FMT(condition, ...) assert(condition)
namespace fextl { template<class T> using vector = std::vector<T>; }
namespace FEXCore::Utils { constexpr uint64_t FEX_PAGE_MASK = ~uint64_t(4095); }
namespace LogMan::Msg { template<class... T> void EFmt(T...) {} }
namespace X86Tables::InstFlags { constexpr unsigned FLAGS_SETS_RIP = 1; }
namespace FEXCore { namespace X86Tables = ::X86Tables; }

struct Info { unsigned Flags {}; };
static Info normal, branch {1};
struct DecodedInst {
  uint64_t PC {};
  Info* TableInfo {};
  uint8_t InstSize {};
  char Padding[111] {};
};
static_assert(sizeof(DecodedInst) == 128);
enum class Status { SUCCESS, INVALID_INST, NOEXEC_INST, PARTIAL_DECODE_INST, BAD_RELOCATION, UNIMPLEMENTED_INST };
struct Op { Status status=Status::SUCCESS; int target=-1; bool stop=false, relocation=false; uint8_t bytes=1; };
struct Disk {
  bool IsReadingDiskCache() const { return false; }
  bool IsWritingDiskCache() const { return false; }
};
struct Context { Disk DiskCache; bool AreMonoHacksActive() const { return false; } };

struct Decoder {
  using DecodedBlockStatus=Status;
  struct DecodedBlocks {
    uint64_t Entry {}, Size {}, NumInstructions {};
    DecodedInst* DecodedInstructions {};
    Status BlockStatus {};
    bool IsEntryPoint {}, ForceFullSMCDetection {};
  };
  struct BlockInformation {
    uint64_t TotalInstructionCount {};
    bool Is64BitMode {};
    std::vector<DecodedBlocks> Blocks;
    std::set<uint64_t> EntryPoints, CodePages;
  } BlockInfo;
  struct Stream {
    const uint8_t* Ptr {};
    Stream& operator+=(size_t n) { Ptr += n; return *this; }
    Stream& operator-=(size_t n) { Ptr -= n; return *this; }
  } InstStream;
  struct Pool {
    DecodedInst* Ptr {}; size_t Bytes {};
    ~Pool() { std::free(Ptr); }
    DecodedInst* ReownOrClaimBuffer(std::optional<size_t> n=std::nullopt) {
      Bytes=n.value_or(65536*sizeof(DecodedInst));
      Ptr=static_cast<DecodedInst*>(std::malloc(Bytes)); assert(Ptr);
      std::memset(static_cast<void*>(Ptr),0,Bytes); return Ptr;
    }
  } PoolObject;
  static constexpr size_t DefaultDecodedBufferSize=65536, MAX_INST_SIZE=15;
  Context context; Context* CTX=&context;
  PES13FexDecodeSet<std::set<uint64_t>> BlocksToDecode, VisitedBlocks, CurrentBlockTargets;
  DecodedInst* DecodedBuffer {}, *DecodeInst {};
  size_t DecodedSize {}, DecodedCapacity {};
  uint64_t MaxInst {}, TotalInstructions {}, PCOffset {}, BlockStartOffset {}, EntryPoint=0x100ff0;
  uint64_t NextBlockStartAddress=~0ULL, CurrentCodePage {}, DecodedMinAddress=~0ULL, DecodedMaxAddress {};
  bool Paused {}, FinalInstruction {}, EntryBlock=true, EraseBlock {}, HitBadRelocation {};
  int64_t BlockResume=-1;
  uint8_t InstructionSize {}, LastFieldReadSize {};
  const void* Relocations=nullptr;
  std::vector<Op> ops;
  std::vector<uint8_t> stream;
  std::vector<uint64_t> visits;
  size_t highest_index {}, calls {};

  Decoder(uint64_t limit,std::vector<Op> input):MaxInst(limit),ops(std::move(input)),stream(ops.size()+32,0x90) {
    // INSERT_REAL_CAPACITY_HERE
    BlocksToDecode.Insert(EntryPoint); BlockInfo.EntryPoints.insert(EntryPoint);
  }
  Stream AdjustAddrForSpecialRegion(const uint8_t* base,uint64_t entry,uint64_t rip) { return {base+(rip-entry)}; }
  std::optional<uint8_t> PeekByte(uint8_t) const { return 0x90; }
  Status DecodeInstruction(uint64_t pc) {
    assert(pc>=EntryPoint && pc-EntryPoint<ops.size());
    highest_index=std::max(highest_index,DecodedSize); ++calls;
    assert(calls<1000000);
    // The write itself is checked by ASan, independently of the loop bound.
    DecodeInst=&DecodedBuffer[DecodedSize]; *DecodeInst={};
    const auto& op=ops[pc-EntryPoint];
    DecodeInst->PC=pc; DecodeInst->InstSize=op.bytes;
    DecodeInst->TableInfo=op.target>=0?&branch:&normal;
    HitBadRelocation=op.relocation;
    visits.push_back(pc);
    return op.status;
  }
  bool InstCanContinue() const {
    const auto& op=ops[DecodeInst->PC-EntryPoint]; return op.target<0 && !op.stop;
  }
  void BranchTargetInMultiblockRange() {
    const auto& op=ops[DecodeInst->PC-EntryPoint];
    for (auto target : {op.target, static_cast<int>(DecodeInst->PC-EntryPoint+op.bytes)}) {
      const uint64_t pc=EntryPoint+target;
      if (target>=0 && static_cast<size_t>(target)<ops.size() && !VisitedBlocks.Contains(pc)) CurrentBlockTargets.Insert(pc);
    }
  }
  bool IsBranchMonoTailcall(uint64_t) const { return false; }
  void DetectDataMasks(uint64_t,DecodedBlocks&) {}
  void PruneInlinedBranchDataMasks() {}
  void DecodeLoop(const uint8_t*,uint64_t=0);
  void run(unsigned pause) {
    do { DecodeLoop(stream.data(),pause); } while(Paused);
  }
};

// INSERT_REAL_LOOP_HERE

static uint64_t digest(const Decoder& d) {
  uint64_t h=1469598103934665603ULL;
  auto mix=[&](uint64_t v) { h=(h^v)*1099511628211ULL; };
  for (auto v:d.visits) mix(v);
  for (const auto& b:d.BlockInfo.Blocks) {
    mix(b.Entry);mix(b.Size);mix(b.NumInstructions);mix(static_cast<unsigned>(b.BlockStatus));
    for (size_t i=0;i<b.NumInstructions;++i) mix(b.DecodedInstructions[i].PC);
  }
  mix(d.BlockInfo.TotalInstructionCount);mix(d.DecodedSize);mix(d.DecodedMinAddress);mix(d.DecodedMaxAddress);
  return h;
}

int main() {
  unsigned cases=0;
  for (uint64_t limit:{0ULL,1ULL,2ULL,127ULL,128ULL,129ULL,500ULL,5000ULL,65535ULL,65536ULL,65537ULL,~0ULL}) {
    for (unsigned mode=0;mode<8;++mode) {
      const size_t count=std::min<uint64_t>(std::max<uint64_t>(limit,1),65536);
      std::vector<Op> ops(count+64);
      if (mode==1) ops[std::min<size_t>(count-1,3)].stop=true;
      if (mode==2) ops[count-1].status=Status::INVALID_INST;
      if (mode==3) ops[0].status=Status::UNIMPLEMENTED_INST;
      if (mode==4) ops[0].relocation=true;
      if (mode==5 || mode==6 || mode==7) {
        if (count>8) {
          ops[2].target=7; ops[4].stop=true;
          if (mode==6) ops[8].status=Status::INVALID_INST;
          if (mode==7) ops[3].bytes=6; // Decode straddles a queued target.
        }
      }
      for (unsigned pause:{0,1,7,63}) {
        Decoder d(limit,ops); d.run(pause);
        assert(d.highest_index<d.PoolObject.Bytes/sizeof(DecodedInst));
        std::printf("%llu %u %u %llu %zu %zu %llu\n",static_cast<unsigned long long>(limit),mode,pause,
          static_cast<unsigned long long>(digest(d)),d.PoolObject.Bytes,d.highest_index,
          static_cast<unsigned long long>(d.BlockInfo.TotalInstructionCount));
        ++cases;
      }
    }
  }
  assert(cases==384);
}
