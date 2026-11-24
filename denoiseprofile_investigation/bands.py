# noise per wavelet scale on a flat patch, against what denoise (profiled)
# assumes
#
#   python3 bands.py <export.pfm> x0 y0 w h a_green b_green
#
# the module normalizes noise to sigma 1 with the green profile entry (for
# all three channels, denoiseprofile.c:1532) and expects sigma_band =
# varf^scale at each a-trous scale (denoiseprofile.c:1564). This applies the
# same 5-tap a-trous filter (without the edge-aware weights, which are
# permissive enough to not matter on a flat patch) and reports the robust
# band sigma in units of sqrt(a_green * mean + b_green).
#
# also prints the band ratios for white noise, derived analytically from
# the filter, to show what varf^scale is not
import math
import statistics as st
import sys

from pfm import crop, plane

H5 = [1 / 16, 4 / 16, 6 / 16, 4 / 16, 1 / 16]
VARF = math.sqrt(2 + 2 * 16 + 36) / 16
NSCALES = 4


def smooth(img, s):
    step = 1 << s
    hh, ww = len(img), len(img[0])
    tmp = [[sum(H5[k] * row[min(max(x + (k - 2) * step, 0), ww - 1)]
                for k in range(5)) for x in range(ww)] for row in img]
    return [[sum(H5[k] * tmp[min(max(y + (k - 2) * step, 0), hh - 1)][x]
                 for k in range(5)) for x in range(ww)] for y in range(hh)]


def band_sigmas(img, nscales):
    out, c = [], img
    for s in range(nscales):
        n = smooth(c, s)
        m = 2 * (2 << s)  # skip the border the filter reaches
        d = [c[y][x] - n[y][x] for y in range(m, len(c) - m)
             for x in range(m, len(c[0]) - m)]
        med = st.median(d)
        out.append(1.4826 * st.median(abs(v - med) for v in d))
        c = n
    return out


def white_ratios(nscales):
    # detail_s = A_s(x)A_s - A_{s+1}(x)A_{s+1} for the separable cumulative
    # 1-D kernels A_s; its energy needs only 1-D norms and inner products
    kernels, offs = [[1.0]], [0]
    for s in range(nscales + 1):
        step = 1 << s
        prev = kernels[-1]
        nxt = [0.0] * (len(prev) + 4 * step)
        for i, v in enumerate(prev):
            for k, wgt in enumerate(H5):
                nxt[i + k * step] += v * wgt
        kernels.append(nxt)
        offs.append(offs[-1] + 2 * step)
    e = []
    for s in range(nscales):
        a, b = kernels[s], kernels[s + 1]
        sh = offs[s + 1] - offs[s]
        aa = sum(v * v for v in a)
        bb = sum(v * v for v in b)
        ab = sum(a[i] * b[i + sh] for i in range(len(a)))
        e.append(aa * aa - 2 * ab * ab + bb * bb)
    return [math.sqrt(v / e[0]) for v in e]


if __name__ == '__main__':
    path = sys.argv[1]
    x0, y0, w, h = map(int, sys.argv[2:6])
    a_g, b_g = float(sys.argv[6]), float(sys.argv[7])
    wr = white_ratios(NSCALES)
    print('white noise ' + '  '.join(f's{k}: {wr[k]:.3f}'
                                     for k in range(NSCALES)))
    print('module      ' + '  '.join(f's{k}: {VARF ** k:.3f}'
                                     for k in range(NSCALES)))
    img = crop(path, x0, y0, w, h)
    for ch, name in enumerate('RGB'):
        p = plane(img, ch)
        m = st.fmean(v for r in p for v in r)
        sp = math.sqrt(a_g * m + b_g)
        s = band_sigmas(p, NSCALES)
        print(f'{name} mean={m:.4f} ' + '  '.join(f's{k}: {s[k] / sp:.2f}'
                                               for k in range(NSCALES)))
