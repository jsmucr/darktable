# robust noise sigma per channel and scale in the module's own detail bands,
# from buffers dumped by the instrumented module on a flat crop
#
#   python3 detail_noise.py <dumpdir> [<dumpdir> ...]
#
# the module expects sigma_band = varf^scale in every channel (times the
# strength scaling); equal values across channels mean the transform
# normalized them alike
import math
import os
import statistics as st
import sys

from pfm import crop

VARF = math.sqrt(70) / 16


def load(path):
    f = open(path, 'rb')
    f.readline()
    w, h = map(int, f.readline().split())
    f.close()
    return crop(path, 0, 0, w, h)


def corr(x, y):
    mx, my = st.fmean(x), st.fmean(y)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    return sxy / (sx * sy)


for d in sys.argv[1:]:
    print(os.path.basename(d.rstrip('/')))
    for s in range(4):
        img = load(f'{d}/detail_{s}.pfm')
        m = 2 * (2 << s)  # the crop edge reads clamped pixels at coarse scales
        vals = []
        for ch in range(3):
            v = [img[y][x][ch] for y in range(m, len(img) - m)
                 for x in range(m, len(img[0]) - m)]
            med = st.median(v)
            vals.append(1.4826 * st.median(abs(x - med) for x in v))
        ratios = (f'ch1/ch0 {vals[1] / vals[0]:.2f},'
                  f' ch2/ch0 {vals[2] / vals[0]:.2f}')
        print(f'  s{s}: ' + '  '.join(f'{x:.3f}' for x in vals)
              + f'   (expects {VARF ** s:.3f}; {ratios})')
    # cross-channel correlation of the finest band
    img = load(f'{d}/detail_0.pfm')
    ch = [[px[c] for r in img[4:-4] for px in r[4:-4]] for c in range(3)]
    print('  s0 correlation ' + '  '.join(
        f'{a}{b} {corr(ch[i], ch[j]):.2f}'
        for (i, a), (j, b) in ((
            (0, '0'), (1, '1')), ((0, '0'), (2, '2')), ((1, '1'), (2, '2')))))
