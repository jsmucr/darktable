# append a crop to a history so that darktable-cli renders, and the pipe
# processes, only a region of P1378616 (5184x3888, no flip or distortion)
#
#   python3 crop_xmp.py <in.xmp> <outdir> [<in.xmp> ...]
#
# writes <outdir>/<name>_<region>.xmp for each region below. Each crop is a
# tradeoff.py measuring region plus MARGIN on every side, so the region sits
# at MARGIN, MARGIN in the render. denoise (profiled) has no modify_roi_in,
# so it sees only the crop: its scale count still follows the full image
# (denoiseprofile.c:917), but the coarse bands are cut at the crop edge and
# the measured band noise comes from the crop alone
import os
import re
import struct
import sys

W, H = 5184, 3888
MARGIN = 300
REGIONS = {  # tradeoff.py regions, x y w h
    'wall': (1900, 500, 360, 260),
    'bird': (2050, 2050, 360, 260),
    'grass': (600, 3300, 360, 260),
}
BLEND = 'gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU='


def crop(x, y, w, h):
    # dt_iop_crop_params_t, version 3: left, top, right, bottom, ratio
    x0, y0 = max(x - MARGIN, 0), max(y - MARGIN, 0)
    x1, y1 = min(x + w + MARGIN, W), min(y + h + MARGIN, H)
    assert (x0, y0) == (x - MARGIN, y - MARGIN)
    b = struct.pack('<4f2i', x0 / W, y0 / H, x1 / W, y1 / H, 0, 0)
    return b.hex()


outdir = sys.argv[2]
for src in sys.argv[1:2] + sys.argv[3:]:
    x = open(src).read()
    end = re.search(r'darktable:history_end="(\d+)"', x)
    n = int(end.group(1))
    tail = '    </rdf:Seq>\n   </darktable:history>'
    assert x.count(tail) == 1
    name = os.path.basename(src).removesuffix('.xmp')
    for region, geo in REGIONS.items():
        s = (f'     <rdf:li darktable:num="{n}"'
             f' darktable:operation="crop" darktable:enabled="1"\n'
             f'      darktable:modversion="3" darktable:params="{crop(*geo)}"'
             f' darktable:multi_name="" darktable:multi_priority="0"\n'
             f'      darktable:blendop_version="14"'
             f' darktable:blendop_params="{BLEND}"/>\n')
        y = x.replace(tail, s + tail, 1).replace(
            end.group(0), f'darktable:history_end="{n + 1}"', 1)
        open(os.path.join(outdir, f'{name}_{region}.xmp'), 'w').write(y)
