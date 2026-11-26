# the Y0 row of the Y0U0V0 matrix with and without DT_DN_Y0FIX
# (y0fix.patch), rendered from the user's own history
#
#   BUILD=<build> python3 y0fix.py <workflow dir> <holiday dir> <workdir> <name>
#
# Renders, all from <name>_1_default.xmp:
#   none          denoise (profiled) off
#   default       their history as it is
#   default_fix   the same with DT_DN_Y0FIX=1
#   dflt          their denoise (profiled) entry at the module's defaults
#                 (wavelets Y0U0V0, strength 1, flat curves, inferred
#                 "preserve shadows" and bias, white-balance-adaptive)
#   dflt_fix      the same with DT_DN_Y0FIX=1
#   dflt_fix_c1   the same with DT_DN_Y0COMP=1 too (no 2.5 compensation)
#   default_fix_c1 their history with both switches
#   dflt_rgb      module defaults in RGB color mode, the "other modes"
#                 the 2.5 was meant to match
# Tile stats as in workflow.py; writes <workdir>/<name>/metrics.json and a
# montage.
import json
import math
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import workflow  # noqa: E402


def default_params(a, color=1):
    # dt_iop_denoiseprofile_params_t v12 as reload_defaults() sets it
    # (variants_xmp.py wav_default)
    radius = float(min(int(1 + a * 15000 + a * a * 300000), 8))
    scattering = min(3000 * a, 1.0)
    shadows = min(max(0.1 - 0.1 * math.log(a), 0.7), 1.8)
    bias = -max(5 + 0.5 * math.log(a), 0.0)
    f = [radius, 7.0, 1.0, shadows, bias, scattering, 0.1, 1.0,
         -1.0, 0, 0, 0, 0, 0]
    b = struct.pack('<14f', *f) + struct.pack('<i', 1)
    b += struct.pack('<42f', *([k / 6.0 for k in range(7)] * 6))
    b += struct.pack('<42f', *([0.5] * 42))
    b += struct.pack('<5i', 1, 1, 1, color, 0)
    assert len(b) == 416
    return b.hex()


def main():
    wf, hol, work, name = sys.argv[1:5]
    d = os.path.join(work, name)
    os.makedirs(os.path.join(d, 'xmp'), exist_ok=True)
    raw = os.path.join(wf, f'{name}_1_default.RW2')
    src = os.path.join(wf, f'{name}_1_default.xmp')
    iso = int(holiday.run(['exiftool', '-s3', '-ISO', raw]).stdout)
    a = holiday.green_a(iso)
    tiles = holiday.pick_tiles(os.path.join(hol, name + '.JPG'))
    fix = {'DT_DN_Y0FIX': '1'}
    fix_c1 = dict(fix, DT_DN_Y0COMP='1')
    renders = {'none': (None, {}, False),
               'default': (None, {}, True),
               'default_fix': (None, fix, True),
               'dflt': (default_params(a), {}, True),
               'dflt_fix': (default_params(a), fix, True),
               'default_fix_c1': (None, fix_c1, True),
               'dflt_fix_c1': (default_params(a), fix_c1, True),
               'dflt_rgb': (default_params(a, 0), {}, True)}
    versions = {}
    for v, (params, env, enabled) in renders.items():
        xmp = os.path.join(d, 'xmp', f'{v}.xmp')
        workflow.variant_xmp(src, xmp, params, enabled)
        out = os.path.join(d, f'{v}.tif')
        if not os.path.exists(out):
            holiday.render(raw, xmp, out, env, core=holiday.TIFF16)
        versions[v] = out
    their = os.path.join(wf, 'export', f'{name}_1_default.tif')
    if os.path.exists(their):
        versions['their_default'] = their

    stats = {}
    for v, full in versions.items():
        for t, (x, y) in tiles.items():
            tile = os.path.join(d, f'{v}_{t}.png')
            holiday.cut(full, x, y, tile)
            stats.setdefault(v, {})[t] = workflow.tile_stats(tile)
    json.dump({'iso': iso, 'tiles': tiles, 'stats': stats},
              open(os.path.join(d, 'metrics.json'), 'w'), indent=1)
    order = [v for v in ('none', 'default', 'default_fix', 'default_fix_c1',
                         'dflt', 'dflt_fix', 'dflt_fix_c1', 'dflt_rgb')
             if v in versions]
    holiday.make_montage(d, tiles, order)


if __name__ == '__main__':
    main()
