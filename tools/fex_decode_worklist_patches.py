"""Reduce decoder bookkeeping allocations without changing decode decisions."""


def apply(replace):
    header = 'FEXCore/Source/Interface/Core/Frontend.h'
    source = 'FEXCore/Source/Interface/Core/Frontend.cpp'
    replace(header, '#include <FEXCore/fextl/set.h>',
            '#include <FEXCore/fextl/set.h>\n#include "horizon_decode_set.h"')
    for name in ('CurrentBlockTargets', 'BlocksToDecode', 'VisitedBlocks'):
        replace(header, f'  fextl::set<uint64_t> {name};',
                f'  PES13FexDecodeSet<fextl::set<uint64_t>> {name};')
    replace(source, 'VisitedBlocks.contains(Target)', 'VisitedBlocks.Contains(Target)')
    replace(source, 'VisitedBlocks.insert(Target)', 'VisitedBlocks.Insert(Target)')
    replace(source, 'CurrentBlockTargets.insert(Target)', 'CurrentBlockTargets.Insert(Target)')
    replace(source, 'BlocksToDecode.empty()', 'BlocksToDecode.Empty()', count=3)
    replace(source, '      auto BlockDecodeIt = BlocksToDecode.begin();\n'
                    '      uint64_t RIPToDecode = *BlockDecodeIt;\n'
                    '      BlocksToDecode.erase(BlockDecodeIt);\n'
                    '      VisitedBlocks.emplace(RIPToDecode);',
                    '      uint64_t RIPToDecode = BlocksToDecode.PopFirst();\n'
                    '      VisitedBlocks.Insert(RIPToDecode);')
    replace(source, '*BlocksToDecode.begin()', 'BlocksToDecode.First()')
    replace(source, 'BlocksToDecode.merge(CurrentBlockTargets)',
                    'BlocksToDecode.MergeAndClear(CurrentBlockTargets)')
    replace(source, 'CurrentBlockTargets.clear()', 'CurrentBlockTargets.Clear()')
    replace(source, 'VisitedBlocks.clear()', 'VisitedBlocks.Clear()')
    replace(source, '  BlocksToDecode = {PC};',
                    '  BlocksToDecode.Clear();\n  BlocksToDecode.Insert(PC);')
