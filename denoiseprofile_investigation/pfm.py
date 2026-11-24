# read a rectangular crop out of a 3-channel PFM without loading the whole file
# (no numpy on the investigation machine; pure python is fast enough for crops)
import array


def crop(path, x0, y0, w, h):
    f = open(path, 'rb')
    if f.readline().strip() != b'PF':
        raise ValueError(f'{path}: not a 3-channel PFM')
    width, height = map(int, f.readline().split())
    f.readline()  # scale; darktable writes little-endian (-1.0)
    off = f.tell()
    out = []
    for y in range(y0, y0 + h):
        row = height - 1 - y  # PFM stores rows bottom-up
        f.seek(off + (row * width + x0) * 12)
        a = array.array('f')
        a.frombytes(f.read(w * 12))
        out.append([(a[3 * i], a[3 * i + 1], a[3 * i + 2]) for i in range(w)])
    return out


def plane(img, ch):
    return [[p[ch] for p in row] for row in img]
