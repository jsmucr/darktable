# summarize holiday.py results by ISO band
#
#   python3 holiday_summary.py <workdir>
#
# per image, from metrics.json, averaged over the two tiles of each kind:
#   noise  flat-tile high-pass RMS over mean, i.e. what is left of the noise
#   detail textured-tile high-pass RMS over mean, relative to no denoise
#          (1 = all of it kept; the no-denoise value includes its noise,
#          so at high ISO even a perfect result stays below 1)
#   specks flat-tile speck count
#   chroma flat-tile Lab a, b spread
# and the camera JPEG's values for the same tiles. Prints one line per
# image and the median per ISO band and variant.
import glob
import json
import os
import statistics as st
import sys

VARIANTS = ['jpeg', 'none', 'old', 'new_s0.75', 'new_s0.9', 'new_s1.1', 'new_s1.2']
BANDS = [(200, 200), (250, 500), (640, 1000), (6400, 25600)]


def summary(d):
    m = d['metrics']
    out = {}
    for v in [v for v in VARIANTS if v in m]:
        f = [m[v][t] for t in m[v] if t.startswith('flat')]
        x = [m[v][t] for t in m[v] if t.startswith('tex')]
        xn = [m['none'][t] for t in m['none'] if t.startswith('tex')]
        out[v] = {
            'noise': st.fmean(t['hp'] for t in f),
            'detail': st.fmean(a['hp'] / b['hp'] for a, b in zip(x, xn)),
            'specks': st.fmean(t['specks'] for t in f),
            'chroma': st.fmean(t['chroma'] for t in f),
        }
    return out


def main():
    work = sys.argv[1]
    rows = []
    for p in sorted(glob.glob(os.path.join(work, '*', 'metrics.json'))):
        d = json.load(open(p))
        if len(d['tiles']) < 4:
            continue
        rows.append((os.path.basename(os.path.dirname(p)), d, summary(d)))
    head = '  '.join(f'{v:>22s}' for v in VARIANTS)
    print(f'{"image":9s} {"ISO":>5s} {"NR":>8s}  {head}')
    print(f'{"":25s}  ' + '  '.join(f'{"noise detail sp chr":>22s}'
                                      for _ in VARIANTS))
    def cell(s, v):
        if v not in s:
            return f'{"-":>22s}'
        return (f'{s[v]["noise"]:6.4f} {s[v]["detail"]:4.2f} '
                f'{s[v]["specks"]:4.0f} {s[v]["chroma"]:4.2f}')

    for name, d, s in sorted(rows, key=lambda r: (r[1]['iso'], r[0])):
        cells = '  '.join(cell(s, v) for v in VARIANTS)
        print(f'{name:9s} {d["iso"]:5d} {d["jpeg_nr"]:>8s}  {cells}')
    print()
    print('median per ISO band')
    for lo, hi in BANDS:
        sel = [s for _, d, s in rows if lo <= d['iso'] <= hi
               and all(v in s for v in VARIANTS)]
        if not sel:
            continue
        cells = '  '.join(
            f'{st.median(s[v]["noise"] for s in sel):6.4f} '
            f'{st.median(s[v]["detail"] for s in sel):4.2f} '
            f'{st.median(s[v]["specks"] for s in sel):4.0f} '
            f'{st.median(s[v]["chroma"] for s in sel):4.2f}'
            for v in VARIANTS)
        print(f'ISO {lo}-{hi} ({len(sel):2d})'.ljust(25) + '  ' + cells)


if __name__ == '__main__':
    main()
