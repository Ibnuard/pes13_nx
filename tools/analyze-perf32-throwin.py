"""Archive the second PERF32 trial, without assigning unrecorded scene labels."""
from pathlib import Path
import importlib.util
import json


def main():
    project = Path(__file__).resolve().parents[1]
    archive = project / 'local/perf32/throwin-result'
    archive.mkdir(parents=True, exist_ok=True)
    source = project / 'dist/pes13-perf32-game-blocks/switch/pes13-nx.log'
    target = archive / 'pes13-nx.log'
    raw = source.read_bytes()
    if target.exists():
        assert target.read_bytes() == raw, 'Refusing to replace archived evidence'
    else:
        target.write_bytes(raw)
    spec = importlib.util.spec_from_file_location('parser', project / 'tools/analyze-perf29-result.py')
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    run = parser.parse(target)
    assert run['build'] == ['pes13-nx-0.2.0-perf32-game-blocks']
    assert run['sampler'] == ['2s/10s at 20ms']
    by_time = {row['uptime_s']: row for row in run['rows']}
    row = None
    for line in raw.decode().splitlines():
        if line.startswith('[PERF8]'):
            row = by_time[parser.numbers(line)['uptime_s']]
        elif row is not None and line.startswith('[PERF32]'):
            row['policy32'] = parser.numbers(line)
    report = dict(
        run=run,
        user_report='No persistent FPS collapse after more than five minutes. '
                    'Throw-in ball held above head feels above 30 FPS; active play below 20.',
        scene_timestamps=None,
        limits=[
            'Present cadence is not simulation speed or unique displayed frames.',
            'CPU sampling is enabled; this is not an uninstrumented benchmark.',
            'Scene timestamps are not encoded in the log.',
            'Thread samples include blocked time and do not equal CPU cycle shares.',
            'A ten-second window can mix gameplay, replay, set pieces and menus.',
            'Sampling covers two seconds per ten seconds, not every frame.',
        ],
    )
    (archive / 'analysis.json').write_text(json.dumps(report, indent=2) + '\n')
    print('sha256', run['sha256'], 'bytes', run['bytes'], 'faults', run['faults'])
    for row in run['rows']:
        gap = row['frames'].get('gap_quiet', {})
        print(row['uptime_s'], 'present/s', round(row['presents'] * 1000 / row['interval_ms'], 2),
              'quiet_gap_ms', round(gap.get('avg_us', 0) / 1000, 2),
              'cores', row.get('cores'),
              'top', sorted(row['threads'].items(), key=lambda item: -item[1])[:4])
    print('last policy', run['rows'][-1].get('policy32'))


if __name__ == '__main__':
    main()
