"""Original FEXTendo ambient loop: deterministic synthesis, no sampled music."""
from pathlib import Path
import array, math, struct, sys, wave
RATE=48000
SECONDS=16

def build(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    frames=RATE*SECONDS
    pcm=[0.0]*frames
    # Four sustained, open voicings; staggered soft plucks. Reverb wraps the loop.
    chords=((50,57,61,66),(47,54,57,62),(43,50,54,59),(45,52,57,62))
    for bar,notes in enumerate(chords):
        for voice,note in enumerate(notes):
            frequency=440*2**((note-69)/12)
            start=int((bar*4+voice*.18)*RATE)
            for i in range(5*RATE):
                t=i/RATE
                envelope=min(1,t/.09)*math.exp(-t/1.35)*(max(0,1-t/5)**2)
                tone=math.sin(math.tau*frequency*t)+.16*math.sin(math.tau*frequency*2*t)
                sample=tone*envelope*.037
                pcm[(start+i)%frames]+=sample
                pcm[(start+i+int(RATE*.31))%frames]+=sample*.19
                pcm[(start+i+int(RATE*.63))%frames]+=sample*.08
    # Blend the seam at a zero amplitude boundary, avoiding a loop click.
    for i in range(480):
        gain=.5-.5*math.cos(math.pi*i/480)
        pcm[i]*=gain;pcm[-1-i]*=gain
    data=array.array('h',(int(max(-.5,min(.5,v))*32767) for v in pcm))
    peak=max(abs(v) for v in data);assert 300<peak<6000
    if sys.byteorder!='little':data.byteswap()
    payload=data.tobytes()
    (out/'background-music.bin').write_bytes(b'FXM1'+struct.pack('<II',RATE,frames)+payload)
    return payload

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--preview',type=Path);a=p.parse_args()
    payload=build(a.output)
    if a.preview:
        with wave.open(str(a.preview),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE);f.writeframes(payload)
