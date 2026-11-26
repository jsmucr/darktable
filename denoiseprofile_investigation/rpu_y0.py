# the Y0 row fix (y0fix.patch) on other cameras: raw.pixls.us samples
# picked by rpu_pick.py, rendered at darktable's defaults (auto-applied
# workflow modules) plus one denoise (profiled) entry at the module's
# defaults
#
#   BUILD=<build> python3 rpu_y0.py <picked.json> <rawdir> <workdir> <model>...
#
# Versions per raw:
#   none     denoise (profiled) off
#   dflt     wavelets Y0U0V0 at module defaults, as darktable ships it
#   fix_c1   the same with DT_DN_Y0FIX=1 DT_DN_Y0COMP=1
#   rgb      wavelets RGB at module defaults (the mode the 2.5 was meant
#            to match)
# Tiles are picked on "none" (25% downscale, as holiday.pick_tiles does);
# per tile the workflow.py stats. Writes <workdir>/<model>/metrics.json,
# a montage, and keeps tiles and JPEGs, not the full TIFFs.
import json
import os
import re
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
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
   darktable:history_end="1">
   <darktable:masks_history>
    <rdf:Seq/>
   </darktable:masks_history>
   <darktable:history>
    <rdf:Seq>
     <rdf:li darktable:num="0" darktable:operation="denoiseprofile"
      darktable:enabled="{enabled}" darktable:modversion="12"
      darktable:params="{params}" darktable:multi_name=""
      darktable:multi_priority="0" darktable:blendop_version="14"
      darktable:blendop_params="{blend}"/>
    </rdf:Seq>
   </darktable:history>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
'''
BLEND = 'gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU='
FIX = {'DT_DN_Y0FIX': '1', 'DT_DN_Y0COMP': '1'}


def green_a(make, model, iso):
    # holiday.green_a for any camera in data/noiseprofiles.json
    d = json.load(open(os.path.join(holiday.SRC, 'data',
                                    'noiseprofiles.json')))
    for mk in d['noiseprofiles']:
        for m in mk['models']:
            if mk['maker'].lower() == make.lower() and \
                    m['model'].lower() == model.lower():
                ps = sorted(m['profiles'], key=lambda p: p['iso'])
    lo = max([p for p in ps if p['iso'] <= iso], key=lambda p: p['iso'],
             default=ps[0])
    hi = min([p for p in ps if p['iso'] >= iso], key=lambda p: p['iso'],
             default=ps[-1])
    if hi['iso'] == lo['iso']:
        return lo['a'][1]
    t = (iso - lo['iso']) / (hi['iso'] - lo['iso'])
    return (1 - t) * lo['a'][1] + t * hi['a'][1]


def fetch(url, path):
    if not os.path.exists(path):
        q = urllib.parse.quote(url, safe=':/')
        with urllib.request.urlopen(q, timeout=600) as r:
            open(path + '.part', 'wb').write(r.read())
        os.rename(path + '.part', path)


def process(r, rawdir, work):
    tag = re.sub(r'\W+', '_', f"{r['make']}_{r['model']}")
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    raw = os.path.join(rawdir, tag + os.path.splitext(r['raw'])[1])
    fetch(r['raw'], raw)
    a = green_a(r['make'], r['model'], r['iso'])
    renders = {'none': (y0fix.default_params(a), {}, 0),
               'dflt': (y0fix.default_params(a), {}, 1),
               'fix_c1': (y0fix.default_params(a), FIX, 1),
               'rgb': (y0fix.default_params(a, 0), {}, 1)}
    full = {}
    for v, (params, env, enabled) in renders.items():
        xmp = os.path.join(d, f'{v}.xmp')
        open(xmp, 'w').write(HEAD.format(enabled=enabled, params=params,
                                         blend=BLEND))
        out = os.path.join(d, f'{v}.tif')
        if not os.path.exists(os.path.join(d, f'{v}.jpg')):
            holiday.render(raw, xmp, out, env, core=holiday.TIFF16)
        full[v] = out
    tiles = holiday.pick_tiles(full['none'])
    stats = {}
    for v, path in full.items():
        for t, (x, y) in tiles.items():
            tile = os.path.join(d, f'{v}_{t}.png')
            holiday.cut(path, x, y, tile)
            stats.setdefault(v, {})[t] = workflow.tile_stats(tile)
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
    os.makedirs(rawdir, exist_ok=True)
    for r in json.load(open(picked)):
        if r['model'] in want:
            print(process(r, rawdir, work), r['iso'], flush=True)


if __name__ == '__main__':
    main()
