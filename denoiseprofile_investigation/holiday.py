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
    run(['convert', full, '-crop', f'{TW}x{TH}+{x}+{y}', '+repage', out])


def tile_metrics(path, kind):
    geo = f'{TW}x{TH}+0+0'
    m = {'hp': tradeoff.hp_rms(path, geo), 'specks': tradeoff.specks(path, geo)}
    if kind == 'flat':
        m['chroma'] = tradeoff.chroma_rms(path, geo)
        m['mottle'] = tradeoff.hp_rms(path, geo, '0x2', '0x16')
    return m


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
    for v in missing:
        entry, env = VARIANTS[v]
        full = os.path.join(d, f'{v}.png')
        render(raw, os.path.join(d, 'xmp', entry + '.xmp'), full, env,
               core=('--conf', 'plugins/imageio/format/png/bpp=16'))
        for t, (x, y) in result['tiles'].items():
            tile = os.path.join(d, f'{v}_{t}.png')
            cut(full, x, y, tile)
            result['metrics'].setdefault(v, {})[t] = tile_metrics(
                tile, t.split('_')[0])
        os.remove(full)
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
        full = os.path.join(d, f'{v}.png')
        render(raw, os.path.join(d, 'xmp', entry + '.xmp'), full, env,
               core=('--conf', 'plugins/imageio/format/png/bpp=16'))
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
