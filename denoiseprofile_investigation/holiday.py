# run old and new denoise (profiled) on a set of G9 raws with their camera
# JPEGs and compare them on automatically chosen flat and textured tiles
#
#   python3 holiday.py <dir with RW2+JPG> <workdir> <name> [<name> ...]
#
# needs bandnoise.patch applied and built in ../build (BUILD=... to
# override). For each image, in <workdir>/<name>/:
#   - tiles: from the camera JPEG, auto-oriented and downscaled 4x so that
#     noise does not count, the two flattest and the two most textured
#     360x260 tiles at mid brightness (flat_0, flat_1, tex_0, tex_1)
#   - exposure: the base history (base_xmp.py, as-shot white balance,
#     capture sharpening autotuned by darktable) gets the exposure that
#     matches the JPEG's mean gray, found by bisection on 1000 px renders
#   - renders: no denoise, old mode at darktable's defaults for this ISO
#     (wav_default), and the session 10 setting at strength 1.1 and 1.2;
#     full frames are cut into the tiles and deleted
#   - metrics.json: per variant and tile, tradeoff.py's high-pass RMS,
#     chroma spread, mottle and speck count; also for the JPEG
#   - montage.jpg: the tiles of every variant beside the JPEG's
# Images are processed three at a time; finished ones are skipped on rerun.
import concurrent.futures
import json
import math
import os
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tradeoff  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
BUILD = os.environ.get('BUILD', os.path.join(SRC, 'build'))
CLI = os.path.join(BUILD, 'bin', 'darktable-cli')
TEMPLATE = os.environ.get('TEMPLATE', os.path.expanduser(
    '~/Pictures/Darktable/20260430_no_name/20260430_0012.RW2.xmp'))
TW, TH = 360, 260
NEW = {'DT_DN_BANDNOISE': '1', 'DT_DN_BNONCE': '1', 'DT_DN_BNLOCAL': '8',
       'DT_DN_BNWIENER': 'y', 'DT_DN_BNLBO': '1', 'DT_DN_DESPECK': '2',
       'DT_DN_BNCGUIDE': '1'}
VARIANTS = {  # name: (variants_xmp.py entry, environment)
    'none': ('none', {}),
    'old': ('wav_default', {}),
    'new_s1.1': ('sw_bnw_s1.1', NEW),
    'new_s1.2': ('sw_bnw_s1.2', NEW),
    # lower strengths, added after the first pass showed 1.1 too strong at
    # low ISO; images already done get only the missing variants
    'new_s0.75': ('sw_bnw_s0.75', NEW),
    'new_s0.9': ('sw_bnw_s0.9', NEW),
    # which part costs texture at low ISO: no despeck, soft thresholding
    # on luma instead of Wiener, both
    'nods_s0.9': ('sw_bnw_s0.9', {**NEW, 'DT_DN_DESPECK': '0'}),
    'soft_s0.9': ('sw_bnw_s0.9', {k: v for k, v in NEW.items()
                                  if k != 'DT_DN_BNWIENER'}),
    'nods_soft_s0.9': ('sw_bnw_s0.9', {k: v for k, v in NEW.items()
                                       if k not in ('DT_DN_BNWIENER',
                                                    'DT_DN_DESPECK')}),
}
# session 11: per-scale noise relative to the finest band, as measured on
# P1378616 (ISO 20000) at strength 1; a cap on the low-ISO estimates
SHAPE = '1.02966 1.00395 1.00448 0.359766 0.692856 0.737432 0.174011 0.439134 0.484474 0.0928742 0.246081 0.271561 0.0566795 0.129975 0.141237 0.0622491 0.0715699 0.0724803 0.0555336 0.0392573 0.0324423'
VARIANTS['shmin_s0.9'] = ('sw_bnw_s0.9', {**NEW, 'DT_DN_BNSHAPE': SHAPE})
VARIANTS['shmin_s1.1'] = ('sw_bnw_s1.1', {**NEW, 'DT_DN_BNSHAPE': SHAPE})
VARIANTS['shset_s1.1'] = ('sw_bnw_s1.1', {**NEW, 'DT_DN_BNSHAPE': SHAPE,
                                          'DT_DN_BNSHAPEMODE': 'set'})
# session 12: the median shape of the 22 images at ISO 640 and up
# (shape_log.py), relative to scale 0 and scaled by each image's own
# scale-0 estimate; a cap on the per-scale estimates
SHAPE_REL = ('1.0000 1.0000 1.0000 0.3792 0.7196 0.7573 0.1866 0.4557 '
             '0.4906 0.0990 0.2518 0.2716 0.0568 0.1310 0.1411 0.0577 '
             '0.0650 0.0678 0.0519 0.0385 0.0300')
for _s in ('0.9', '1.1', '1.2'):
    VARIANTS[f'rel_s{_s}'] = (f'sw_bnw_s{_s}', {
        **NEW, 'DT_DN_BNSHAPE': SHAPE_REL, 'DT_DN_BNSHAPEREL': '1'})
# session 12 ablation at strength 0.75, ISO 200: per-channel exponents,
# no guide, window r 4, no local thresholds at all (session 6 BayesShrink
# with measured noise)
VARIANTS['abl_bn_s0.75'] = ('sw_bn_s0.75', NEW)
VARIANTS['abl_noguide_s0.75'] = ('sw_bnw_s0.75', {
    k: v for k, v in NEW.items() if k != 'DT_DN_BNCGUIDE'})
VARIANTS['abl_r4_s0.75'] = ('sw_bnw_s0.75', {**NEW, 'DT_DN_BNLOCAL': '4'})
VARIANTS['abl_global_s0.75'] = ('sw_bnw_s0.75', {
    'DT_DN_BANDNOISE': '1', 'DT_DN_BNONCE': '1'})
VARIANTS['abl_global_s1.1'] = ('sw_bnw_s1.1', {
    'DT_DN_BANDNOISE': '1', 'DT_DN_BNONCE': '1'})
# session 13: luma by a fixed soft threshold at k sigma (BNLUMAK), mixed
# with the Wiener result at weight w (BNLUMAW); with the session 12 shape
# cap. Chroma as before
REL = {**NEW, 'DT_DN_BNSHAPE': SHAPE_REL, 'DT_DN_BNSHAPEREL': '1'}
for _k in ('0.5', '1.0', '1.5'):
    VARIANTS[f'soft{_k}_s1.0'] = ('sw_bnw_s1.0', {**REL, 'DT_DN_BNLUMAK': _k})
VARIANTS['mix1.0_s1.0'] = ('sw_bnw_s1.0', {**REL, 'DT_DN_BNLUMAK': '1.0',
                                          'DT_DN_BNLUMAW': '0.5'})
VARIANTS['mix1.0_s1.1'] = ('sw_bnw_s1.1', {**REL, 'DT_DN_BNLUMAK': '1.0',
                                          'DT_DN_BNLUMAW': '0.5'})
# session 13 diagnostics: chroma detail kept; old mode's shadows and
# chroma curve (wav_default) with measured noise
VARIANTS['ckeep_s1.0'] = ('sw_bnw_s1.0', {**REL, 'DT_DN_BNCHROMAKEEP': '1'})
VARIANTS['newdef_s1.0'] = ('wav_default', {**REL})
for _f in ('bnwi', 'bnwc5', 'bnwic5'):
    VARIANTS[f'{_f}_s1.0'] = (f'sw_{_f}_s1.0', REL)
VARIANTS['bnwi_s0.9'] = ('sw_bnwi_s0.9', REL)
VARIANTS['bnwi_s0.6'] = ('sw_bnwi_s0.6', REL)
VARIANTS['bnwi_s0.75'] = ('sw_bnwi_s0.75', REL)
VARIANTS['bnwi_s1.1'] = ('sw_bnwi_s1.1', REL)
# HOLIDAY_TILES=1: render measured-noise variants as crops of the tiles
# (render_tiles()), 4 small renders instead of a full frame. Does not match
# full frames with DT_DN_BNLOCAL=8 (session 13): the coarse-scale windows
# reach far beyond the margin. Kept for settings with small windows only
TILE_RENDER = os.environ.get('HOLIDAY_TILES') == '1'
# HOLIDAY_VARIANTS=a,b,...: render only these (plus what a new image needs)
if os.environ.get('HOLIDAY_VARIANTS'):
    _keep = os.environ['HOLIDAY_VARIANTS'].split(',')
    VARIANTS = {k: v for k, v in VARIANTS.items() if k in _keep}


def run(args, env=None, **kw):
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(args, env=e, check=True, capture_output=True,
                          text=True, **kw)


def green_a(iso):
    # the green "a" of the G9 profile at this ISO, interpolated as
    # dt_noiseprofile_interpolate() does (src/common/noiseprofiles.c:377);
    # variants_xmp.py infers the old mode's defaults from it
    d = json.load(open(os.path.join(SRC, 'data', 'noiseprofiles.json')))
    for mk in d['noiseprofiles']:
        for m in mk['models']:
            if m['model'] == 'DC-G9':
                ps = sorted(m['profiles'], key=lambda p: p['iso'])
    lo = max([p for p in ps if p['iso'] <= iso], key=lambda p: p['iso'],
             default=ps[0])
    hi = min([p for p in ps if p['iso'] >= iso], key=lambda p: p['iso'],
             default=ps[-1])
    if hi['iso'] == lo['iso']:
        return lo['a'][1]
    t = (iso - lo['iso']) / (hi['iso'] - lo['iso'])
    return (1 - t) * lo['a'][1] + t * hi['a'][1]


def render(raw, xmp, out, env=None, cli=(), core=()):
    # cli: darktable-cli options, which must come before --core; core:
    # darktable options after it
    with tempfile.TemporaryDirectory() as cfg:
        if os.path.exists(out):
            os.remove(out)
        run([CLI, raw, xmp, out, '--apply-custom-presets', 'false', *cli,
             '--core', '--configdir', cfg, '--library', ':memory:', *core],
            env)


def mean_gray(path):
    return float(run(['convert', path, '-auto-orient', '-colorspace', 'gray',
                      '-format', '%[fx:mean]', 'info:']).stdout)


def pick_tiles(jpg):
    # tile structure on the 4x downscaled JPEG: high-pass RMS over mean
    w, h = map(int, run(['identify', '-format', '%w %h', '-auto-orient',
                         jpg]).stdout.split()[:2])
    out = run(['convert', jpg, '-auto-orient', '-colorspace', 'gray',
               '-resize', '25%', '(', '+clone', '-blur', '0x3', ')',
               '-compose', 'mathematics', '-define',
               'compose:args=0,1,-1,0.5', '-composite',
               # no +repage: %X %Y are the tile offsets
               '-crop', f'{TW // 4}x{TH // 4}',
               '-format', '%X %Y %[fx:standard_deviation]\n', 'info:']).stdout
    means = run(['convert', jpg, '-auto-orient', '-colorspace', 'gray',
                 '-resize', '25%', '-crop', f'{TW // 4}x{TH // 4}',
                 '-format', '%[fx:mean] %w %h\n', 'info:']).stdout.split('\n')
    tiles = []
    for line, m in zip(out.strip().split('\n'), means):
        x, y, sd = line.split()
        mean, tw, th = m.split()
        x, y = int(x.lstrip('+')) * 4, int(y.lstrip('+')) * 4
        mean = float(mean)
        if int(tw) < TW // 4 or int(th) < TH // 4 or not 0.12 < mean < 0.88:
            continue
        # keep off the outer 5%: lens corrections in the JPEG move them most
        if x < 0.05 * w or y < 0.05 * h or x + TW > 0.95 * w \
                or y + TH > 0.95 * h:
            continue
        tiles.append((float(sd) / mean, x, y))
    tiles.sort()
    flat = [t for t in tiles[:2]]
    tex = [t for t in tiles[-2:][::-1]]
    return {f'flat_{i}': (x, y) for i, (_, x, y) in enumerate(flat)} | \
           {f'tex_{i}': (x, y) for i, (_, x, y) in enumerate(tex)}


def cut(full, x, y, out):
    # one 16-bit tile; measuring on it instead of the full frame avoids
    # reloading a 120 MB PNG for every metric
    run(['convert', '-quiet', full, '-crop', f'{TW}x{TH}+{x}+{y}', '+repage',
         out])


def tile_metrics(path, kind):
    geo = f'{TW}x{TH}+0+0'
    m = {'hp': tradeoff.hp_rms(path, geo), 'specks': tradeoff.specks(path, geo)}
    if kind == 'flat':
        m['chroma'] = tradeoff.chroma_rms(path, geo)
        m['mottle'] = tradeoff.hp_rms(path, geo, '0x2', '0x16')
    return m


MARGIN = 300  # around each tile in crop renders, as crop_xmp.py
# full-frame renders as uncompressed 16-bit TIFF: faster to write and to
# cut tiles from than 16-bit PNG, same pixels (session 13)
TIFF16 = ('--conf', 'plugins/imageio/format/tiff/bpp=16',
          '--conf', 'plugins/imageio/format/tiff/compress=0')
BLEND = 'gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU='


def pin_capture(s, radius, thrs):
    # capture sharpening autotunes when its radius is 0, and on a crop it
    # would tune to the crop: write the full frame's values into the
    # demosaic entry (cs_radius and cs_thrs, bytes 24-31 of params v8)
    li = re.search(r'<rdf:li\s[^>]*?darktable:operation="demosaic"[^>]*?/>',
                   s, re.S).group(0)
    p = re.search(r'params="([0-9a-f]+)"', li).group(1)
    b = bytearray(bytes.fromhex(p))
    b[24:32] = struct.pack('<2f', radius, thrs)
    return s.replace(li, li.replace(p, b.hex()), 1)


def crop_xmp(xmp, out, x, y, w, h, capture):
    # the history plus a crop to the tile and MARGIN around it, in the
    # oriented output's coordinates (crop runs after flip); returns the
    # tile's offset in the cropped render
    x0, y0 = max(x - MARGIN, 0), max(y - MARGIN, 0)
    x1, y1 = min(x + TW + MARGIN, w), min(y + TH + MARGIN, h)
    p = struct.pack('<4f2i', x0 / w, y0 / h, x1 / w, y1 / h, 0, 0).hex()
    s = pin_capture(open(xmp).read(), *capture)
    n = int(re.search(r'darktable:history_end="(\d+)"', s).group(1))
    li = (f'     <rdf:li darktable:num="{n}" darktable:operation="crop"'
          ' darktable:enabled="1"\n'
          f'      darktable:modversion="3" darktable:params="{p}"'
          ' darktable:multi_name="" darktable:multi_priority="0"\n'
          f'      darktable:blendop_version="14"'
          f' darktable:blendop_params="{BLEND}"/>\n')
    end = '    </rdf:Seq>\n   </darktable:history>'
    s = s.replace(end, li + end, 1).replace(
        f'darktable:history_end="{n}"', f'darktable:history_end="{n + 1}"')
    open(out, 'w').write(s)
    return x - x0, y - y0


def fixed_noise(raw, xmp, d, env):
    # the full frame's band noise for this transform and despeck level, in
    # the units DT_DN_BNFIXED takes (as logged, per-scale values divided by
    # strength); with DT_DN_BNONCE the estimate does not depend on strength
    key = os.path.basename(xmp).split('_s')[0] + '_ds' + env.get(
        'DT_DN_DESPECK', '0')
    cache = os.path.join(d, 'xmp', f'bnfixed_{key}.txt')
    capfile = os.path.join(d, 'xmp', 'capture.txt')
    if not os.path.exists(cache) or not os.path.exists(capfile):
        e = {'DT_DN_BANDNOISE': '1', 'DT_DN_BNONCE': '1',
             'DT_DN_BANDNOISE_LOG': '1'}
        if 'DT_DN_DESPECK' in env:
            e['DT_DN_DESPECK'] = env['DT_DN_DESPECK']
        with tempfile.TemporaryDirectory() as cfg:
            err = run([CLI, raw, xmp, os.path.join(cfg, 'x.png'),
                       '--apply-custom-presets', 'false', '--core',
                       '--configdir', cfg, '--library', ':memory:',
                       '-d', 'pipe'], e)
            err = err.stderr + err.stdout
        s = float(re.search(r'_s([0-9.]+)\.xmp$', xmp).group(1))
        v = list(re.search(r'scale-0 noise (\S+) (\S+) (\S+),',
                           err).groups())
        for m in re.finditer(r'scale \d+ noise x strength (\S+) (\S+) (\S+)',
                             err):
            v += [str(float(t) / s) for t in m.groups()]
        open(cache, 'w').write(' '.join(v[:24]))
        m = re.search(r'autotuned capture.*threshold=(\S+) radius=(\S+)', err)
        open(capfile, 'w').write(f'{m.group(2)} {m.group(1)}')
    radius, thrs = map(float, open(capfile).read().split())
    return open(cache).read(), (radius, thrs)


def render_tiles(raw, xmp, d, v, env, tiles, size):
    # measured-noise variants: render only the tiles, with the full frame's
    # band noise passed in so that they match a full-frame render
    if 'DT_DN_BANDNOISE' not in env:
        return False
    fixed, capture = fixed_noise(raw, xmp, d, env)
    env = dict(env, DT_DN_BNFIXED=fixed)
    w, h = size

    def one(t):
        x, y = tiles[t]
        cx = os.path.join(d, 'xmp', f'crop_{v}_{t}.xmp')
        ox, oy = crop_xmp(xmp, cx, x, y, w, h, capture)
        tmp = os.path.join(d, f'crop_{v}_{t}.png')
        render(raw, cx, tmp, env,
               core=('--conf', 'plugins/imageio/format/png/bpp=16'))
        cut(tmp, ox, oy, os.path.join(d, f'{v}_{t}.png'))
        os.remove(tmp)
        os.remove(cx)

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        list(ex.map(one, tiles))
    return True


def add_variants(src, d, name):
    # render the variants a finished image lacks, with its stored tiles
    # and exposure
    result = json.load(open(os.path.join(d, 'metrics.json')))
    missing = [v for v in VARIANTS if v not in result['metrics']]
    if not missing:
        return name, 'cached'
    raw = os.path.join(src, name + '.RW2')
    base = os.path.join(d, 'xmp', 'base.xmp')
    run(['python3', os.path.join(HERE, 'variants_xmp.py'), base,
         str(green_a(result['iso'])), os.path.join(d, 'xmp')])
    size = result.get('size') or [int(t) for t in run(
        ['identify', '-format', '%w %h', '-auto-orient',
         os.path.join(src, name + '.JPG')]).stdout.split()[:2]]
    for v in missing:
        entry, env = VARIANTS[v]
        xmp = os.path.join(d, 'xmp', entry + '.xmp')
        if not (TILE_RENDER and render_tiles(raw, xmp, d, v, env,
                                             result['tiles'], size)):
            full = os.path.join(d, f'{v}.tif')
            render(raw, xmp, full, env, core=TIFF16)
            for t, (x, y) in result['tiles'].items():
                cut(full, x, y, os.path.join(d, f'{v}_{t}.png'))
            os.remove(full)
        for t in result['tiles']:
            result['metrics'].setdefault(v, {})[t] = tile_metrics(
                os.path.join(d, f'{v}_{t}.png'), t.split('_')[0])
    make_montage(d, result['tiles'], list(result['metrics']))
    json.dump(result, open(os.path.join(d, 'metrics.json'), 'w'), indent=1)
    return name, 'added ' + ' '.join(missing)


def make_montage(d, tiles, names):
    # names: every variant rendered so far, the JPEG first
    cells = []
    for t in tiles:
        for v in names:
            cells += ['-label', f'{v} {t}', os.path.join(d, f'{v}_{t}.png')]
    run(['montage', *cells, '-tile', f'{len(names)}x', '-geometry',
         '+3+3', '-quality', '90', os.path.join(d, 'montage.jpg')])


def process(src, work, name):
    d = os.path.join(work, name)
    if os.path.exists(os.path.join(d, 'metrics.json')):
        return add_variants(src, d, name)
    os.makedirs(os.path.join(d, 'xmp'), exist_ok=True)
    raw, jpg = os.path.join(src, name + '.RW2'), os.path.join(src, name + '.JPG')
    iso = int(run(['exiftool', '-s3', '-ISO', raw]).stdout)
    nr = run(['exiftool', '-s3', '-NoiseReduction', jpg]).stdout.strip()

    # a copy of the JPEG with its orientation applied, so that pixel
    # coordinates match darktable's output
    ojpg = os.path.join(d, 'jpeg.png')
    run(['convert', jpg, '-auto-orient', ojpg])
    tiles = pick_tiles(jpg)

    # exposure by bisection: the mean gray of a 1000 px render, no denoise
    # and no sharpening, against the JPEG's
    target = mean_gray(jpg)
    lo, hi = -2.0, 6.0
    small = os.path.join(d, 'small.png')
    base = os.path.join(d, 'xmp', 'base.xmp')
    for _ in range(7):
        ev = 0.5 * (lo + hi)
        run(['python3', os.path.join(HERE, 'base_xmp.py'), TEMPLATE, base,
             str(ev)])
        render(raw, base, small, cli=('--width', '1000', '--height', '1000'))
        if mean_gray(small) < target:
            lo = ev
        else:
            hi = ev
    ev = round(0.5 * (lo + hi), 2)
    os.remove(small)
    run(['python3', os.path.join(HERE, 'base_xmp.py'), TEMPLATE, base,
         str(ev), 'auto'])
    run(['python3', os.path.join(HERE, 'variants_xmp.py'), base,
         str(green_a(iso)), os.path.join(d, 'xmp')])

    result = {'iso': iso, 'jpeg_nr': nr, 'ev': ev, 'tiles': tiles,
              'metrics': {}}
    for t, (x, y) in tiles.items():
        tile = os.path.join(d, f'jpeg_{t}.png')
        cut(ojpg, x, y, tile)
        result['metrics'].setdefault('jpeg', {})[t] = tile_metrics(
            tile, t.split('_')[0])
    for v, (entry, env) in VARIANTS.items():
        full = os.path.join(d, f'{v}.tif')
        render(raw, os.path.join(d, 'xmp', entry + '.xmp'), full, env,
               core=TIFF16)
        for t, (x, y) in tiles.items():
            tile = os.path.join(d, f'{v}_{t}.png')
            cut(full, x, y, tile)
            result['metrics'].setdefault(v, {})[t] = tile_metrics(
                tile, t.split('_')[0])
        os.remove(full)
    os.remove(ojpg)

    make_montage(d, tiles, list(result['metrics']))
    json.dump(result, open(os.path.join(d, 'metrics.json'), 'w'), indent=1)
    return name, f'ISO {iso} EV {ev}'


def main():
    src, work, names = sys.argv[1], sys.argv[2], sys.argv[3:]
    os.makedirs(work, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        futs = [ex.submit(process, src, work, n) for n in names]
        for f in concurrent.futures.as_completed(futs):
            try:
                print(*f.result(), flush=True)
            except subprocess.CalledProcessError as e:
                print('failed:', e.cmd[:3], e.stderr[-400:], flush=True)


if __name__ == '__main__':
    main()
