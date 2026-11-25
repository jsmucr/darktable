# lightness energy per spatial band, flat tiles against textured tiles,
# relative to no denoise, median per ISO band (session 12)
#
#   python3 holiday_bands.py [workdir]
#
# bands of Lab L: fine (pixel minus blur 1), mid (blur 1 minus blur 3),
# coarse (blur 3 minus blur 8), on holiday.py's tiles
import sys
import json, glob, os, subprocess, statistics as st, concurrent.futures, collections
BANDS=[('fine 0-1px','0','0x1'),('mid 1-3px','0x1','0x3'),('coarse 3-8px','0x3','0x8')]
def band(p, a, b):
    pre=['-blur',a] if a!='0' else []
    o=subprocess.run(['convert',p,'-colorspace','Lab','-channel','R','-separate','+channel',*pre,'(', '+clone','-blur',b,')','-compose','mathematics','-define','compose:args=0,1,-1,0.5','-composite','-format','%[fx:standard_deviation]','info:'],capture_output=True,text=True,check=True).stdout
    return float(o)
V=['none','old','new_s0.75','new_s1.1','jpeg']
jobs=[]
for p in sorted(glob.glob(os.path.join(sys.argv[1] if len(sys.argv) > 1 else '/tmp/hol/run', '*', 'metrics.json'))):
    d=os.path.dirname(p); iso=json.load(open(p))['iso']
    for v in V:
        for t in ('flat_0','flat_1','tex_0','tex_1'):
            for bn,a,b in BANDS: jobs.append((os.path.basename(d),iso,v,t,bn,f'{d}/{v}_{t}.png',a,b))
with concurrent.futures.ThreadPoolExecutor(16) as ex:
    res=list(ex.map(lambda j: (*j[:5], band(*j[5:])), jobs))
D=collections.defaultdict(dict)
for n,iso,v,t,bn,x in res: D[(n,iso)][(v,t,bn)]=x
for lab,(lo,hi) in (('200',(200,200)),('250-500',(250,500)),('640-1000',(640,1000)),('6400+',(6400,99999))):
    sel=[k for k in D if lo<=k[1]<=hi]
    print(f'ISO {lab} ({len(sel)}): band RMS relative to no denoise, flat | textured')
    for v in V[1:]:
        cells=[]
        for bn,_,_ in BANDS:
            f=st.median(st.fmean(D[k][(v,t,bn)]/D[k][('none',t,bn)] for t in ('flat_0','flat_1')) for k in sel)
            x=st.median(st.fmean(D[k][(v,t,bn)]/D[k][('none',t,bn)] for t in ('tex_0','tex_1')) for k in sel)
            cells.append(f'{bn}: {f:.2f} | {x:.2f}')
        print(f'   {v:10s} '+'   '.join(cells))
