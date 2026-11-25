# compare the user's own workflow renders (session 14): their default
# (chroma-only denoise), raw neural denoise, Topaz, against the
# measured-noise mode rendered from their own history
#
#   python3 workflow.py <workflow dir> <holiday dir> <workdir> <name> ...
#
# <workflow dir> holds <name>_1_default.RW2 + .xmp and export/*.tif
# (GUIDE.txt there). Renders, with this build and bandnoise.patch applied:
#   none     their history with denoise (profiled) off
#   default  their history as it is (a check against their export)
#   new_sX   their denoise (profiled) entry replaced by the session 13
#            setting at strength X: wavelets Y0U0V0, flat curves, "preserve
#            shadows" inferred from the profile, one transform exponent,
#            with the measured-noise switches below
# Tiles are chosen on the camera JPEG as in holiday.py. Per tile: Lab L
# energy in the fine (0-1 px) and mid (1-3 px) bands, relative to "none",
# speck count, chroma spread. Writes <workdir>/<name>/metrics.json and a
# montage of the tiles of every version.
import concurrent.futures
import json
import math
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import tradeoff  # noqa: E402

NEW = {'DT_DN_BANDNOISE': '1', 'DT_DN_BNONCE': '1', 'DT_DN_BNLOCAL': '8',
       'DT_DN_BNWIENER': 'y', 'DT_DN_BNLBO': '1', 'DT_DN_DESPECK': '2',
       'DT_DN_BNCGUIDE': '1'}
# strengths per image, around what matched the reference noise level in
# session 13 for that ISO
STRENGTHS = {200: (0.6, 0.75), 800: (0.75, 0.9), 6400: (0.9, 1.0),
             20000: (1.0, 1.1), 25600: (1.0, 1.1)}


def denoiseprofile(a, strength):
    # dt_iop_denoiseprofile_params_t v12 as variants_xmp.py writes it:
    # wavelets, Y0U0V0, flat curves, shadows/bias/radius/scattering
    # inferred from the profile's green a as reload_defaults() does
    # (src/iop/denoiseprofile.c:2647), wb_adaptive_anscombe off
    radius = float(min(int(1 + a * 15000 + a * a * 300000), 8))
    scattering = min(3000 * a, 1.0)
    shadows = min(max(0.1 - 0.1 * math.log(a), 0.7), 1.8)
    bias = -max(5 + 0.5 * math.log(a), 0.0)
    f = [radius, 7.0, strength, shadows, bias, scattering, 0.1, 1.0,
         -1.0, 0, 0, 0, 0, 0]
    b = struct.pack('<14f', *f) + struct.pack('<i', 1)
    b += struct.pack('<42f', *([k / 6.0 for k in range(7)] * 6))
    b += struct.pack('<42f', *([0.5] * 42)) + struct.pack('<5i', 0, 1, 1, 1, 0)
    assert len(b) == 416
    return b.hex()


def entry(x, op):
    return re.search(r'<rdf:li\s[^>]*?darktable:operation="%s"[^>]*?/>' % op,
                     x, re.S).group(0)


def variant_xmp(src, out, params=None, enabled=True):
    # the user's history with their denoise (profiled) entry changed
    x = open(src).read()
    li = entry(x, 'denoiseprofile')
    new = re.sub(r'darktable:enabled="\d"',
                 f'darktable:enabled="{1 if enabled else 0}"', li)
    if params:
        new = re.sub(r'darktable:params="[^"]+"',
                     f'darktable:params="{params}"', new)
    open(out, 'w').write(x.replace(li, new, 1))


def lband(path, a, b):
    pre = ['-blur', a] if a != '0' else []
    return float(holiday.run(
        ['convert', '-quiet', path, '-colorspace', 'Lab', '-channel', 'R',
         '-separate', '+channel', *pre, '(', '+clone', '-blur', b, ')',
         '-compose', 'mathematics', '-define', 'compose:args=0,1,-1,0.5',
         '-composite', '-format', '%[fx:standard_deviation]', 'info:']).stdout)


def tile_stats(path):
    geo = f'{holiday.TW}x{holiday.TH}+0+0'
    return {'fine': lband(path, '0', '0x1'), 'mid': lband(path, '0x1', '0x3'),
            'specks': tradeoff.specks(path, geo),
            'chroma': tradeoff.chroma_rms(path, geo)}


def process(wf, hol, work, name):
    d = os.path.join(work, name)
    os.makedirs(os.path.join(d, 'xmp'), exist_ok=True)
    raw = os.path.join(wf, f'{name}_1_default.RW2')
    src = os.path.join(wf, f'{name}_1_default.xmp')
    iso = int(holiday.run(['exiftool', '-s3', '-ISO', raw]).stdout)
    a = holiday.green_a(iso)
    tiles = holiday.pick_tiles(os.path.join(hol, name + '.JPG'))

    versions = {}  # name: (full-size tif, needs deleting)
    for f in sorted(os.listdir(os.path.join(wf, 'export'))):
        m = re.match(rf'{name}_(\d)_(\w+)\.tif$', f)
        if m:
            versions[f'their_{m.group(2)}'] = (
                os.path.join(wf, 'export', f), False)
    renders = {'none': (None, {}, False), 'default': (None, {}, True)}
    for s in STRENGTHS[iso]:
        renders[f'new_s{s}'] = (denoiseprofile(a, s), NEW, True)
    for v, (params, env, enabled) in renders.items():
        xmp = os.path.join(d, 'xmp', f'{v}.xmp')
        variant_xmp(src, xmp, params, enabled)
        out = os.path.join(d, f'{v}.tif')
        if not os.path.exists(out):
            holiday.render(raw, xmp, out, env, core=holiday.TIFF16)
        versions[v] = (out, False)

    stats = {}
    for v, (full, _) in versions.items():
        for t, (x, y) in tiles.items():
            tile = os.path.join(d, f'{v}_{t}.png')
            holiday.cut(full, x, y, tile)
            stats.setdefault(v, {})[t] = tile_stats(tile)
    result = {'iso': iso, 'tiles': tiles, 'strengths': STRENGTHS[iso],
              'stats': stats}
    json.dump(result, open(os.path.join(d, 'metrics.json'), 'w'), indent=1)
    order = ['none', 'their_default', 'default'] + \
        sorted(v for v in versions if v.startswith('their_neural')) + \
        [v for v in versions if v == 'their_topaz'] + \
        sorted(v for v in versions if v.startswith('new_'))
    holiday.make_montage(d, tiles, order)
    return name, iso


def main():
    wf, hol, work, names = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
    os.makedirs(work, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        for name, iso in ex.map(lambda n: process(wf, hol, work, n), names):
            print(name, iso, flush=True)


if __name__ == '__main__':
    main()
