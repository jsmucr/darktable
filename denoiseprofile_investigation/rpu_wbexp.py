# the white-balance-adaptive transform (per-channel exponents) against
# one exponent with everything else unchanged (wbexp.patch,
# DT_DN_WBEXP=1), with and without capture sharpening, on the samples
# rpu_pick.py picked
#
#   BUILD=<build> python3 rpu_wbexp.py <picked.json> <rawdir> <workdir> <model>...
#
# Versions per raw, each with capture sharpening off (no suffix) and on
# (_cs; demosaic RCD, radius 0 so darktable autotunes it, threshold 0.45):
#   none   denoise (profiled) off
#   ship   wavelets Y0U0V0 at the module's defaults
#   eq     the same with DT_DN_WBEXP=1
#   off    the same with the "whitebalance-adaptive transform" toggle off
#          (also changes the matrices: session 10's comparison)
# Env: WBX_STRENGTH (default 1.0) sets the denoise strength; WBX_EXTRA
# "name:x,y;..." adds fixed tiles (top-left corners) to the picked ones.
# Per tile: workflow.py's stats, plus the chroma that follows the luma
# texture in the 1-16 px band (as tradeoff.rock_chroma, computed in
# python): its correlations with L and "locked" =
# 100 sqrt((corr_a sd_a)^2 + (corr_b sd_b)^2), the part of the a, b band
# amplitude explained by L. Rerunning recomputes the stats from the kept
# tiles without rendering.
import array
import json
import math
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import rpu_y0  # noqa: E402
import workflow  # noqa: E402
import y0fix  # noqa: E402

HEAD = '''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:darktable="http://darktable.sf.net/"
   darktable:xmp_version="5"
   darktable:raw_params="0"
   darktable:auto_presets_applied="0"
   darktable:history_end="{n}"
   darktable:history_basic_hash="0123456789abcdef0123456789abcdef"
   darktable:history_current_hash="0123456789abcdef0123456789abcdef">
   <darktable:masks_history>
    <rdf:Seq/>
   </darktable:masks_history>
   <darktable:history>
    <rdf:Seq>
{items}    </rdf:Seq>
   </darktable:history>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
'''
ITEM = '''     <rdf:li darktable:num="{num}" darktable:operation="{op}"
      darktable:enabled="{enabled}" darktable:modversion="{ver}"
      darktable:params="{params}" darktable:multi_name=""
      darktable:multi_priority="0" darktable:blendop_version="14"
      darktable:blendop_params="{blend}"/>
'''


# equal basic and current hashes make the history count as unaltered
# (dt_image_altered(), src/common/image.c:1998), which capture
# sharpening needs before it autotunes (src/iop/demosaic.c:925); checked
# to change nothing else in a render


def demosaic_cs():
    # dt_iop_demosaic_params_t v8 at its defaults (RCD, which falls back to
    # Markesteijn on X-Trans) with capture sharpening on; radius 0 makes
    # darktable autotune it (base_xmp.py)
    b = struct.pack('<ifiiiffffififfi', 0, 0.0, 0, 5, 1, 0.2,
                    0.0, 0.45, 0.0, 8, 0.0, 1, 0.0, 0.0, 1)
    assert len(b) == 60
    return b.hex()


def xmp(path, items):
    s = ''.join(ITEM.format(num=k, op=op, enabled=en, ver=ver, params=p,
                            blend=rpu_y0.BLEND)
                for k, (op, ver, p, en) in enumerate(items))
    open(path, 'w').write(HEAD.format(n=len(items), items=s))


def _band(path, ch):
    # the 1-16 px band of one Lab channel, as 16-bit samples around 32768;
    # the statistics are taken in python because ImageMagick Q16 quantizes
    # a per-pixel product (tradeoff.rock_chroma's -fx) at these amplitudes
    raw = subprocess.run(
        ['convert', '-quiet', path, '-colorspace', 'Lab', '-channel', ch,
         '-separate', '+channel', '-blur', '0x1', '(', '+clone', '-blur',
         '0x16', ')', '-compose', 'mathematics', '-define',
         'compose:args=0,1,-1,0.5', '-composite', '-depth', '16',
         '-endian', 'LSB', 'gray:-'], capture_output=True, check=True).stdout
    v = array.array('H', raw)
    if sys.byteorder != 'little':
        v.byteswap()
    return [(x - 32768) / 65535 for x in v]


def texture_lock(path):
    L, a, b = (_band(path, ch) for ch in 'RGB')
    n = len(L)

    def stats(x, y):
        mx, my = sum(x) / n, sum(y) / n
        sxy = sum((p - mx) * (q - my) for p, q in zip(x, y)) / n
        return sxy

    vl, va, vb = stats(L, L), stats(a, a), stats(b, b)
    ca = stats(L, a) / math.sqrt(vl * va) if vl * va > 0 else 0.0
    cb = stats(L, b) / math.sqrt(vl * vb) if vl * vb > 0 else 0.0
    return {'band_chroma': 100 * math.sqrt(va + vb), 'corr_a': ca,
            'corr_b': cb,
            'locked': 100 * math.sqrt(ca * ca * va + cb * cb * vb)}


def process(r, rawdir, work):
    tag = re.sub(r'\W+', '_', f"{r['make']}_{r['model']}")
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    raw = os.path.join(rawdir, tag + os.path.splitext(r['raw'])[1])
    rpu_y0.fetch(r['raw'], raw)
    a = rpu_y0.green_a(r['make'], r['model'], r['iso'])
    s = float(os.environ.get('WBX_STRENGTH', '1.0'))
    dn = {'none': (y0fix.default_params(a), {}, 0),
          'ship': (y0fix.default_params(a, strength=s), {}, 1),
          'eq': (y0fix.default_params(a, strength=s), {'DT_DN_WBEXP': '1'},
                 1),
          'off': (y0fix.default_params(a, wbadapt=0, strength=s), {}, 1)}
    names = [v + cs for cs in ('', '_cs') for v in dn]
    old = os.path.join(d, 'metrics.json')
    if os.path.exists(old):
        tiles = json.load(open(old))['tiles']
        stats = {}
        for v in names:
            for t in tiles:
                tile = os.path.join(d, f'{v}_{t}.png')
                st = workflow.tile_stats(tile)
                st.update(texture_lock(tile))
                stats.setdefault(v, {})[t] = st
        json.dump({'sample': r, 'a': a, 'tiles': tiles, 'stats': stats},
                  open(old, 'w'), indent=1)
        return tag
    full = {}
    for cs in ('', '_cs'):
        for v, (params, env, en) in dn.items():
            name = v + cs
            items = [('demosaic', 8, demosaic_cs(), 1)] if cs else []
            items.append(('denoiseprofile', 12, params, en))
            x = os.path.join(d, f'{name}.xmp')
            xmp(x, items)
            out = os.path.join(d, f'{name}.tif')
            if not os.path.exists(os.path.join(d, f'{name}.jpg')):
                holiday.render(raw, x, out, env, core=holiday.TIFF16)
            full[name] = out
    tiles = holiday.pick_tiles(full['none'])
    for e in filter(None, os.environ.get('WBX_EXTRA', '').split(';')):
        n, xy = e.split(':')
        tiles[n] = [int(v) for v in xy.split(',')]
    stats = {}
    for v, path in full.items():
        for t, (x, y) in tiles.items():
            tile = os.path.join(d, f'{v}_{t}.png')
            holiday.cut(path, x, y, tile)
            st = workflow.tile_stats(tile)
            st.update(texture_lock(tile))
            stats.setdefault(v, {})[t] = st
    json.dump({'sample': r, 'a': a, 'tiles': tiles, 'stats': stats},
              open(os.path.join(d, 'metrics.json'), 'w'), indent=1)
    holiday.make_montage(d, tiles, list(full))
    for v, path in full.items():
        holiday.run(['convert', '-quiet', path, '-quality', '90',
                     os.path.join(d, f'{v}.jpg')])
        os.remove(path)
    return tag


def main():
    picked, rawdir, work = sys.argv[1:4]
    want = set(sys.argv[4:])
    for r in json.load(open(picked)):
        if r['model'] in want:
            print(process(r, rawdir, work), r['iso'], flush=True)


if __name__ == '__main__':
    main()
