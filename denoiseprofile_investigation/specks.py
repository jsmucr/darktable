# trace dark specks through the buffers dumped by the instrumented module
# (denoiseprofile_investigation/instrumentation.patch, DT_DN_DUMP/DT_DN_CROP)
#
#   python3 specks.py <dumpdir> <scale-0 luma threshold>
#
# a speck is a module-output pixel whose luminance is below 0.65x the median
# of its 5x5 neighborhood. For each, report where it already stood out:
# in the module input, after the variance-stabilizing transform, and in
# the finest detail band against the threshold. Channel 0 of the
# transformed and detail buffers is Y0 in Y0U0V0 mode.
import statistics as st
import sys

from pfm import crop

d, thr0 = sys.argv[1], float(sys.argv[2])


def load(name):
    f = open(f'{d}/{name}.pfm', 'rb')
    f.readline()
    w, h = map(int, f.readline().split())
    f.close()
    return crop(f'{d}/{name}.pfm', 0, 0, w, h)


def lum(p):
    return 0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2]


out, inp = load('output'), load('input')
tr, det = load('transformed'), load('detail_0')
H, W = len(out), len(out[0])


def nb(img, x, y, f):
    return [f(img[y + j][x + i]) for j in range(-2, 3) for i in range(-2, 3)]


def mad(v):
    m = st.median(v)
    return 1.4826 * st.median(abs(x - m) for x in v)


specks = []
for y in range(2, H - 2):
    for x in range(2, W - 2):
        if lum(out[y][x]) < 0.65 * st.median(nb(out, x, y, lum)):
            specks.append((x, y))
print(f'{len(specks)} specks in {(W - 4) * (H - 4)} pixels')

# global robust sigma of transformed Y0 against its local median, for z-scores
res = [tr[y][x][0] - st.median(nb(tr, x, y, lambda p: p[0]))
       for y in range(2, H - 2, 3) for x in range(2, W - 2, 3)]
s_tr = mad(res)
dv = [det[y][x][0] for y in range(H) for x in range(W)]
s_det = mad(dv)
print(f'detail_0 Y0: robust sigma {s_det:.3f}, threshold {thr0:.3f}'
      f' = {thr0 / s_det:.2f} sigma')
neg = sum(v < -thr0 for v in dv)
pos = sum(v > thr0 for v in dv)
print(f'coefficients beyond the threshold: {neg} negative, {pos} positive')

print(' x   y  | input lum/med  min ch | input z | transformed z |'
      ' detail_0/thr')
s_in = mad([lum(inp[y][x]) - st.median(nb(inp, x, y, lum))
            for y in range(2, H - 2, 3) for x in range(2, W - 2, 3)])
for x, y in specks[:25]:
    il = lum(inp[y][x]) / st.median(nb(inp, x, y, lum))
    mn = min(inp[y][x])
    zi = (lum(inp[y][x]) - st.median(nb(inp, x, y, lum))) / s_in
    z = (tr[y][x][0] - st.median(nb(tr, x, y, lambda p: p[0]))) / s_tr
    print(f'{x:3d} {y:3d} | {il:6.2f} {mn:9.5f} | {zi:7.2f} | {z:7.2f} |'
          f' {det[y][x][0] / thr0:6.2f}')

zs = [(tr[y][x][0] - st.median(nb(tr, x, y, lambda p: p[0]))) / s_tr
      for x, y in specks]
zi = [(lum(inp[y][x]) - st.median(nb(inp, x, y, lum))) / s_in
      for x, y in specks]
print(f'specks: median input z {st.median(zi):.2f},'
      f' median transformed z {st.median(zs):.2f},'
      f' {sum(z < -3 for z in zs)}/{len(zs)} below -3 sigma after transform')
