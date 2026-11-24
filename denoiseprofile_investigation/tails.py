# tail asymmetry of the noise before and after the variance-stabilizing
# transform, on the dumped buffers of a flat crop
#
#   python3 tails.py <dumpdir>
#
# residual = pixel minus the median of its 5x5 neighborhood, in units of
# the robust sigma of those residuals. Gaussian noise gives about 0.13%
# beyond each of +-3 sigma and 0.003% beyond +-4, symmetric. Also counts
# input values that are exactly 0, which nothing in the module produces.
import statistics as st
import sys

from pfm import crop

d = sys.argv[1]


def load(name):
    f = open(f'{d}/{name}.pfm', 'rb')
    f.readline()
    w, h = map(int, f.readline().split())
    f.close()
    return crop(f'{d}/{name}.pfm', 0, 0, w, h)


def tails(img, ch, label):
    H, W = len(img), len(img[0])
    r = []
    for y in range(2, H - 2, 2):
        for x in range(2, W - 2, 2):
            nb = [img[y + j][x + i][ch] for j in range(-2, 3)
                  for i in range(-2, 3)]
            r.append(img[y][x][ch] - st.median(nb))
    m = st.median(r)
    s = 1.4826 * st.median(abs(v - m) for v in r)
    n = len(r)
    lo3 = 100 * sum(v < -3 * s for v in r) / n
    hi3 = 100 * sum(v > 3 * s for v in r) / n
    lo4 = 100 * sum(v < -4 * s for v in r) / n
    hi4 = 100 * sum(v > 4 * s for v in r) / n
    print(f'{label:22s} <-3s {lo3:5.2f}%  >+3s {hi3:5.2f}%'
          f'   <-4s {lo4:5.2f}%  >+4s {hi4:5.2f}%')


inp, tr = load('input'), load('transformed')
for ch, n in enumerate('RGB'):
    tails(inp, ch, f'input {n}')
for ch, n in enumerate(('Y0', 'U0', 'V0')):
    tails(tr, ch, f'transformed {n}')
H, W = len(inp), len(inp[0])
for ch, n in enumerate('RGB'):
    z = sum(inp[y][x][ch] == 0.0 for y in range(H) for x in range(W))
    neg = sum(inp[y][x][ch] < 0.0 for y in range(H) for x in range(W))
    print(f'input {n}: {100 * z / (H * W):.2f}% exactly 0,'
          f' {100 * neg / (H * W):.2f}% negative')
