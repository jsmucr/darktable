# lightness energy in the fine and mid bands, flat and textured tiles,
# relative to no denoise, plus flat-tile specks and chroma; medians per
# ISO group, for a chosen list of holiday.py variants (session 13)
#
#   python3 holiday_cmp.py <file with image names> <variant,variant,...>
#
# RUN=... sets holiday.py's workdir (default /tmp/hol/run)
import json, sys, statistics as st, subprocess, concurrent.futures, os
RUN = os.environ.get('RUN', '/tmp/hol/run')  # holiday.py's workdir
names=open(sys.argv[1]).read().split(); V=sys.argv[2].split(',')
def lband(p,a,b):
    pre=['-blur',a] if a!='0' else []
    o=subprocess.run(['convert',p,'-colorspace','Lab','-channel','R','-separate','+channel',*pre,'(', '+clone','-blur',b,')','-compose','mathematics','-define','compose:args=0,1,-1,0.5','-composite','-format','%[fx:standard_deviation]','info:'],capture_output=True,text=True,check=True).stdout
    return float(o)
jobs=[(n,v,t) for n in names for v in set(V+['none']) for t in ('flat_0','flat_1','tex_0','tex_1')]
def f(j):
    n,v,t=j; p=f'{RUN}/{n}/{v}_{t}.png'
    return j, (lband(p,'0','0x1'), lband(p,'0x1','0x3'))
with concurrent.futures.ThreadPoolExecutor(16) as ex: R=dict(ex.map(f,jobs))
iso={n:json.load(open(f'{RUN}/{n}/metrics.json'))['iso'] for n in names}
for lab,g in (('ISO 200',lambda i:i==200),('ISO 640-1000',lambda i:200<i<=1000),('ISO 6400+',lambda i:i>=6400)):
    sel=[n for n in names if g(iso[n])]
    print(f'{lab} ({len(sel)}): L fine band flat | tex   mid band flat | tex   (relative to no denoise)   specks(flat)  chroma(flat)')
    for v in V:
        fine_f=st.median(st.fmean(R[(n,v,t)][0]/R[(n,'none',t)][0] for t in ('flat_0','flat_1')) for n in sel)
        fine_x=st.median(st.fmean(R[(n,v,t)][0]/R[(n,'none',t)][0] for t in ('tex_0','tex_1')) for n in sel)
        mid_f=st.median(st.fmean(R[(n,v,t)][1]/R[(n,'none',t)][1] for t in ('flat_0','flat_1')) for n in sel)
        mid_x=st.median(st.fmean(R[(n,v,t)][1]/R[(n,'none',t)][1] for t in ('tex_0','tex_1')) for n in sel)
        m=[json.load(open(f'{RUN}/{n}/metrics.json'))['metrics'][v] for n in sel]
        sp=st.median(st.fmean(x[t]['specks'] for t in ('flat_0','flat_1')) for x in m)
        ch=st.median(st.fmean(x[t]['chroma'] for t in ('flat_0','flat_1')) for x in m)
        print(f'   {v:14s} {fine_f:.2f} | {fine_x:.2f}      {mid_f:.2f} | {mid_x:.2f}      {sp:6.0f}  {ch:.2f}')
