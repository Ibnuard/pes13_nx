"""Reproduce the kick-off candidate's physical frame and pipeline observations."""
from pathlib import Path
import argparse, hashlib, json, re

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log',type=Path);ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();raw=a.log.read_bytes();text=raw.decode(errors='replace');windows=[]
    for line in text.splitlines():
        if line.startswith('[FEX3-PACE] elapsed_ms='):
            row={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)}
            row['host_presents_per_second']=round(row['ok']*1000/row['window_ms'],3) if row['window_ms'] else None
            row['stages']={};windows.append(row)
        elif (line.startswith('[FEX3-PACE] ') or line.startswith('[FEX3-PIPE] ')) and 'bins=' in line:
            row={k:int(v) for k,v in re.findall(r'(n|avg_us|peak_since_launch_us)=(\d+)',line)}
            row['bins']=list(map(int,line.split('bins=')[1].split(',')))
            windows[-1]['stages'][line.split()[1]]=row
    assert windows and all(len(w['stages'])==9 for w in windows)
    for w in windows:
        for stage in w['stages'].values(): assert sum(stage['bins'])==stage['n']
    report={'input_sha256':hashlib.sha256(raw).hexdigest(),'input_bytes':len(raw),
            'build':re.search(r'^\[BUILD\] (.+)$',text,re.M)[1].strip(),
            'user_report':{'kickoff_pause':'scoreboard appears, brief stop then motion resumes',
                'clocks':'stock initially; CPU-only OC after approximately three minutes; no logged change marker',
                'speed':'user confirms scoreboard time remains stable; 3D motion appears doubled/jumpy'},
            'windows':windows,'last_elapsed_ms':windows[-1]['elapsed_ms'],
            'peaks_us':{k:max(w['stages'][k]['peak_since_launch_us'] for w in windows) for k in windows[0]['stages']},
            'limitations':['Presents are API calls, not distinct displayed frames or simulation updates.',
                'elapsed_ms starts at the first flusher report, not application startup.',
                'Clock change and kick-off timestamps are approximate; phases are not a controlled OC benchmark.',
                'Wait/driver metrics are CPU wall time including scheduling; nested or concurrent values cannot be added as CPU load.',
                'Clock-page update cadence does not measure game-side animation time or prove every guest timer correct.'],
            'next_change':'Targeted Horizon event/mutex/semaphore notifications for select waiters; preserve broad self-suspend/start gates and all timeout/result semantics.',
            'hardware_fix_verified':False}
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='windows'},indent=2))
if __name__=='__main__':main()
