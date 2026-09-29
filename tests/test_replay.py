import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPLAY = ROOT / 'outputs/replay_stream.json'
VK = ('T', 'P', 'R')


def test_replay_matches_scored_stream():
    replay = json.loads(REPLAY.read_text())
    metrics = json.loads((ROOT / 'outputs/metrics.json').read_text())
    assert REPLAY.stat().st_size < 3e6
    assert len(pd.read_parquet(ROOT / 'outputs/scored_stream.parquet', columns=['p_fault'])) == metrics['dataset']['rows']
    rows, segs = replay['rows'], replay['segments']
    for g, seg in enumerate(segs):
        r = [x for x in rows if x['g'] == g]
        assert seg['counts']['rows'] == len(r) > 0
        assert seg['counts']['alerts'] == sum(x['p'] >= replay['alert_threshold'] for x in r)
        empty = [x for x in r if all(x[k] is None for k in VK)]
        assert not empty or (seg.get('event', {}).get('cls') == 'F7' and all(x['f'] == 'F7' for x in empty))
        assert all(x['e'].startswith('No observation received') and 'sigma' not in x['e'] for x in empty)
        if seg['kind'] in ('heatwave', 'monsoon'):
            assert all(x['f'] is None for x in r)
    classes = {s['event']['cls'] for s in segs if 'event' in s}
    assert classes >= {f'F{i}' for i in range(1, 10)}
    assert any(s['event']['missed'] for s in segs if 'event' in s)
