# fit var = a * x + b to the output of tools/noise/noiseprofile.c, weighted
# by bin population like darktable-gen-noiseprofile's gnuplot fit, and
# compare a with a profile
#
#   python3 profile_fit.py <file.dat> a_r a_g a_b
import sys

path = sys.argv[1]
prof = list(map(float, sys.argv[2:5]))
rows = [list(map(float, line.split())) for line in open(path)]


def fit(ch):
    s = sx = sy = sxx = sxy = 0.0
    for r in rows:
        x, w, y = r[0], r[4 + ch], r[1 + ch] ** 2
        if w < 1000 or x <= 0:
            continue
        s += w
        sx += w * x
        sy += w * y
        sxx += w * x * x
        sxy += w * x * y
    a = (s * sxy - sx * sy) / (s * sxx - sx * sx)
    return a, (sy - a * sx) / s


print('  '.join(f'{c}: a={fit(k)[0]:.3e} b={fit(k)[1]:.2e}'
                f' ({fit(k)[0] / prof[k]:.2f}x profile)'
                for k, c in enumerate('RGB')))
