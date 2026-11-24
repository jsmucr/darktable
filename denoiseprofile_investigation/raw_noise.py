# raw photosite noise on a flat patch of the CFA export (see profiling_xmp.py)
#
#   python3 raw_noise.py cfa.pfm x0 y0 w h a_r a_g a_b b_r b_g b_b
#
# per 2x2 CFA phase: mean, robust noise sigma, and how the noise averages
# under 2x2 and 4x4 binning of the same-color plane (white noise: 0.25 and
# 0.0625), next to the sigma the profile predicts at that mean
import math
import statistics as st
import sys

from pfm import crop, plane

path = sys.argv[1]
x0, y0, w, h = map(int, sys.argv[2:6])
pa = list(map(float, sys.argv[6:9]))
pb = list(map(float, sys.argv[9:12]))


def robust_sigma(img):
    # residual against the 4-neighbor mean; var = 1.25 sigma^2 for white noise
    d = [img[i][j] - (img[i - 1][j] + img[i + 1][j]
                      + img[i][j - 1] + img[i][j + 1]) / 4
         for i in range(1, len(img) - 1) for j in range(1, len(img[0]) - 1)]
    med = st.median(d)
    return 1.4826 * st.median(abs(v - med) for v in d) / math.sqrt(1.25)


def binned(img, n):
    hh, ww = len(img) // n, len(img[0]) // n
    return [[sum(img[i * n + a][j * n + b] for a in range(n) for b in range(n))
             / (n * n) for j in range(ww)] for i in range(hh)]


v = plane(crop(path, x0, y0, w, h), 0)
for py in (0, 1):
    for px in (0, 1):
        sub = [row[px::2] for row in v[py::2]]
        flat = [x for r in sub for x in r]
        m = st.fmean(flat)
        s1 = robust_sigma(sub)
        r2 = robust_sigma(binned(sub, 2)) ** 2 / s1 ** 2
        r4 = robust_sigma(binned(sub, 4)) ** 2 / s1 ** 2
        clipped = 100 * sum(x <= 0 for x in flat) / len(flat)
        prof = ' '.join(f'{c}={math.sqrt(pa[k] * m + pb[k]):.5f}'
                        for k, c in enumerate('RGB'))
        print(f'phase({py},{px}) mean={m:.4f} sigma={s1:.5f}'
              f' bin2={r2:.3f} bin4={r4:.4f} <=0: {clipped:.1f}%'
              f'  profile sigma {prof}')
