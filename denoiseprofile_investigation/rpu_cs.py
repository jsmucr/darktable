# does capture sharpening's contrast threshold (cs_thrs, autotuned from the
# EXIF ISO, clamped at ISO 1000: src/iop/demosaicing/capture.c
# _get_variance_threshold) let noise through on high-ISO files, and which
# threshold would stop it? On the 15 samples of rpu_pick.py plus the G9
# ISO 20000 file P1378616 (tag Panasonic_DC_G9_P1378616)
#
#   BUILD=<build> python3 rpu_cs.py <picked.json> <rawdir> <tilesdir> \
#       <workdir> [<tag>...]
#
# needs a build with csmask.patch (DT_CS_DUMP=<file.pfm> writes capture
# sharpening's mask and prints a "capture mask WxH+dx+dy thrs= radius=
# mean= above_half=" line, always, without -d). <tilesdir> is the
# extracted rpu_wbexp.py output (wbexp.tar members wbx/<tag>/metrics.json
# and wbx3p/Panasonic_DC_G9/metrics.json for P1378616): its "tiles" are
# reused, so the tiles match that session (P1378616 also has rock, wall).
# No tag arguments: all 16 images (the picked.json entries that have tiles
# in <tilesdir>, plus P1378616), one after the other; two renders at a
# time within an image. Finished versions are skipped on rerun.
#
# Per image, in <workdir>/<tag>/:
#   auto run: denoise off, capture sharpening on, radius 0 (darktable
#     autotunes), -d pipe: "autotuned capture threshold= radius=" gives
#     thrs_auto and radius_auto, the "capture mask" line the mask mean and
#     above_half (the fraction of the mask above 0.5). The threshold and
#     radius are taken from the mask line (3 decimals)
#   sweep, radius pinned to radius_auto (nonzero, so no autotune), cs_thrs
#     t in auto, 0.6, 0.8, 1.0, with denoise (profiled) off (cs_<t>_off) and
#     on (cs_<t>_dn: y0fix.default_params(a), the module's defaults, no env
#     switches), plus capture sharpening off (demosaic entry absent): none
#     (denoise off) and ship (denoise defaults)
#   the XMP is rpu_wbexp's (equal history hashes, needed for autotune);
#   demosaic params v8 as rpu_wbexp.demosaic_cs() but with cs_radius and
#     cs_thrs (7th and 8th fields) set
#   renders are 16-bit uncompressed TIFF, cut into the stored tiles
#     (<version>_<tile>.png) and deleted; DT_CS_DUMP is set for the auto
#     run and the cs_*_off renders (mask_<t>.pfm, kept only until the
#     coverage line is read; mask_<t>.png is the 4x downscaled 8-bit mask
#     in the demosaic buffer's coordinates, i.e. before flip)
#   workflow.tile_stats per tile and version (fine, mid, specks, chroma)
#   metrics.json: sample, a, tiles, auto (thrs, radius, mean, above_half),
#     mask (per threshold: thrs, mean, above_half, size), stats
#   montage.jpg: the tiles in the order none, cs_auto_off, cs_0.6_off,
#     cs_0.8_off, cs_1.0_off, ship, cs_auto_dn, cs_0.6_dn, cs_0.8_dn,
#     cs_1.0_dn; masks.jpg: the four masks
# <workdir>/summary.txt (also printed): per image the ISO, thrs_auto,
# radius_auto, mask mean per threshold; for denoise off and on, per
# version: flat-tile fine luma and textured-tile mid luma relative to
# "none" (mean of the per-tile ratios), flat-tile specks relative to
# "none" (totals; the absolute count of none in brackets); and the lowest
# swept threshold whose flat-tile fine luma is within 5% above that of the
# same denoise setting without sharpening (none for off, ship for dn),
# or "none".
# Rerunning with all versions' tiles present recomputes the summary only.
import concurrent.futures
import json
import os
import re
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import rpu_wbexp  # noqa: E402
import rpu_y0  # noqa: E402
import workflow  # noqa: E402
import y0fix  # noqa: E402

THRS = ['auto', '0.6', '0.8', '1.0']
ORDER = (['none'] + [f'cs_{t}_off' for t in THRS] + ['ship']
         + [f'cs_{t}_dn' for t in THRS])
P1378616 = {'make': 'Panasonic', 'model': 'DC-G9', 'iso': 20000,
            'raw': 'file:///c/temp/denoise/P1378616.RW2'}
P1378616_TAG = 'Panasonic_DC_G9_P1378616'
TOL = 1.05


def demosaic(radius, thrs):
    # dt_iop_demosaic_params_t v8 at its defaults (rpu_wbexp.demosaic_cs)
    # with capture sharpening on, cs_radius and cs_thrs set
    b = struct.pack('<ifiiiffffififfi', 0, 0.0, 0, 5, 1, 0.2,
                    radius, thrs, 0.0, 8, 0.0, 1, 0.0, 0.0, 1)
    assert len(b) == 60
    return b.hex()


def cli_render(raw, xmp, out, env, debug=False):
    # holiday.render, returning darktable's output
    with tempfile.TemporaryDirectory() as cfg:
        if os.path.exists(out):
            os.remove(out)
        r = holiday.run([holiday.CLI, raw, xmp, out,
                         '--apply-custom-presets', 'false', '--core',
                         '--configdir', cfg, '--library', ':memory:',
                         *holiday.TIFF16, *(['-d', 'pipe'] if debug else [])],
                        env)
        return r.stdout + r.stderr


MASK = re.compile(r'capture mask (\d+)x(\d+)\+(-?\d+)\+(-?\d+) thrs=(\S+) '
                  r'radius=(\S+) mean=(\S+) above_half=(\S+)')


def parse_mask(text):
    m = MASK.findall(text)
    if len(m) != 1:
        raise RuntimeError(f'{len(m)} capture mask lines: {text[-600:]}')
    w, h, dx, dy, thrs, radius, mean, half = m[0]
    return {'size': [int(w), int(h)], 'offset': [int(dx), int(dy)],
            'thrs': float(thrs), 'radius': float(radius),
            'mean': float(mean), 'above_half': float(half)}


def mask_png(pfm, png):
    holiday.run(['convert', '-quiet', pfm, '-resize', '25%', '-depth', '8',
                 png])


def summarize(results, out):
    def ratio(st, v, kinds, key, base='none'):
        r = [st[v][t][key] / st[base][t][key] for t in st[v]
             if t.split('_')[0] in kinds and st[base][t][key] > 0]
        return sum(r) / len(r) if r else float('nan')

    def specks(st, v, base='none'):
        tot = lambda n: sum(st[n][t]['specks'] for t in st[n]
                            if t.startswith('flat'))
        return tot(v), tot(base)

    lines = []
    for r in results:
        if r is None:
            continue
        a, st, mk = r['auto'], r['stats'], r['mask']
        lines.append(f"{r['tag']}  ISO {r['sample']['iso']}  "
                     f"thrs_auto {a['thrs']:.2f}  radius_auto "
                     f"{a['radius']:.3f}  mask mean "
                     + '  '.join(f"{t}:{mk[t]['mean']:.4f}" for t in THRS))
        lines.append('   (flat = flat tiles, fine luma; tex = textured '
                     'tiles, mid luma; both relative to none; '
                     'specks: flat tiles relative to none [count in none])')
        for block, sfx, ref in (('denoise off', 'off', 'none'),
                                ('denoise on', 'dn', 'ship')):
            names = ([ref] if sfx == 'dn' else []) + \
                [f'cs_{t}_{sfx}' for t in THRS]
            lines.append(f'   {block}:')
            for v in names:
                sp, sp0 = specks(st, v)
                lines.append(
                    f'     {v:<12} flat {ratio(st, v, ("flat",), "fine"):6.3f}'
                    f'  tex {ratio(st, v, ("tex",), "mid"):6.3f}'
                    f'  specks {sp / sp0 if sp0 else float("nan"):6.3f}'
                    f' [{sp0}]')
            lowest = 'none'
            for t in THRS:
                v = f'cs_{t}_{sfx}'
                if ratio(st, v, ('flat',), 'fine', ref) <= TOL:
                    lowest = t if t != 'auto' else f"auto ({a['thrs']:.2f})"
                    break
            lines.append(f'     lowest threshold with flat fine luma within '
                         f'5% of {ref}: {lowest}')
        lines.append('')
    open(out, 'w').write('\n'.join(lines))
    return '\n'.join(lines)


def process(r, tag, raw, tilesfile, work):
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    a = rpu_y0.green_a(r['make'], r['model'], r['iso'])
    tiles = {k: tuple(v) for k, v in
             json.load(open(tilesfile))['tiles'].items()}
    cov = os.path.join(d, 'coverage.json')
    info = json.load(open(cov)) if os.path.exists(cov) else {'mask': {}}

    def save():
        json.dump(info, open(cov, 'w'), indent=1)

    if 'auto' not in info:
        x = os.path.join(d, 'auto.xmp')
        rpu_wbexp.xmp(x, [('demosaic', 8, demosaic(0.0, 0.45), 1),
                          ('denoiseprofile', 12, y0fix.default_params(a), 0)])
        pfm = os.path.join(d, 'mask_auto_run.pfm')
        out = os.path.join(d, 'auto.tif')
        text = cli_render(raw, x, out, {'DT_CS_DUMP': pfm}, debug=True)
        os.remove(out)
        m = re.search(r'autotuned capture.*threshold=(\S+) radius=(\S+)', text)
        if not m:
            raise RuntimeError('no autotune line: ' + text[-600:])
        info['auto'] = dict(parse_mask(text), log_thrs=float(m.group(1)),
                            log_radius=float(m.group(2)))
        os.remove(pfm)
        save()
    radius = info['auto']['radius']
    thr = {'auto': info['auto']['thrs'], '0.6': 0.6, '0.8': 0.8, '1.0': 1.0}

    def one(v):
        tilepng = lambda t: os.path.join(d, f'{v}_{t}.png')
        if all(os.path.exists(tilepng(t)) for t in tiles):
            return
        env, items = {}, []
        m = re.match(r'cs_(.+)_(off|dn)$', v)
        dn = v == 'ship' or bool(m and m.group(2) == 'dn')
        if m:
            items.append(('demosaic', 8, demosaic(radius, thr[m.group(1)]), 1))
            if not dn:
                pfm = os.path.join(d, f'mask_{m.group(1)}.pfm')
                env['DT_CS_DUMP'] = pfm
        items.append(('denoiseprofile', 12, y0fix.default_params(a),
                      int(dn)))
        x = os.path.join(d, f'{v}.xmp')
        rpu_wbexp.xmp(x, items)
        out = os.path.join(d, f'{v}.tif')
        text = cli_render(raw, x, out, env)
        for t, (tx, ty) in tiles.items():
            holiday.cut(out, tx, ty, tilepng(t))
        os.remove(out)
        if 'DT_CS_DUMP' in env:
            info['mask'][m.group(1)] = parse_mask(text)
            mask_png(env['DT_CS_DUMP'], os.path.join(
                d, f'mask_{m.group(1)}.png'))
            os.remove(env['DT_CS_DUMP'])
            save()

    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        list(ex.map(one, ORDER))
    stats = {v: {t: workflow.tile_stats(os.path.join(d, f'{v}_{t}.png'))
                 for t in tiles} for v in ORDER}
    res = {'tag': tag, 'sample': r, 'a': a, 'tiles': tiles,
           'auto': info['auto'], 'mask': info['mask'], 'stats': stats}
    json.dump(res, open(os.path.join(d, 'metrics.json'), 'w'), indent=1)
    holiday.make_montage(d, tiles, ORDER)
    holiday.run(['montage', *[p for t in THRS for p in (
        '-label', f'{t} thrs={info["mask"][t]["thrs"]:.2f} mean='
        f'{info["mask"][t]["mean"]:.3f}', os.path.join(d, f'mask_{t}.png'))],
        '-tile', '4x', '-geometry', '+3+3', '-quality', '90',
        os.path.join(d, 'masks.jpg')])
    return res


def main():
    picked, rawdir, tilesdir, work = sys.argv[1:5]
    want = set(sys.argv[5:])
    # the switches of the earlier sessions must not leak into a render
    for k in [k for k in os.environ if k.startswith('DT_DN_')
              or k == 'DT_CS_DUMP']:
        del os.environ[k]
    os.makedirs(work, exist_ok=True)
    jobs = []
    for r in json.load(open(picked)):
        tag = re.sub(r'\W+', '_', f"{r['make']}_{r['model']}")
        tf = os.path.join(tilesdir, 'wbx', tag, 'metrics.json')
        # picked.json lists every camera; the images are those with tiles
        if os.path.exists(tf):
            jobs.append((r, tag, os.path.join(
                rawdir, tag + os.path.splitext(r['raw'])[1]), tf))
    jobs.append((P1378616, P1378616_TAG, '/c/temp/denoise/P1378616.RW2',
                 os.path.join(tilesdir, 'wbx3p', 'Panasonic_DC_G9',
                              'metrics.json')))
    for r, tag, raw, tf in jobs:
        if want and tag not in want:
            continue
        try:
            process(r, tag, raw, tf, work)
            print(tag, r['iso'], 'done', flush=True)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            print('failed:', tag, getattr(e, 'stderr', None) or e, flush=True)
    # the summary covers every image with a metrics.json in <workdir>
    results = []
    for r, tag, raw, tf in jobs:
        f = os.path.join(work, tag, 'metrics.json')
        results.append(json.load(open(f)) if os.path.exists(f) else None)
    print(summarize(results, os.path.join(work, 'summary.txt')))


if __name__ == '__main__':
    main()
