# task cswf: the user's own histories (workflow dir), varying only capture
# sharpening's threshold, to find a per-ISO threshold for their setup.
#
#   BUILD=<build> python3 rpu_cswf.py <workflow dir> <holiday dir> <workdir> \
#       <resultdir> [<name>...]
#
# <workflow dir>: <name>_1_default.RW2 + .xmp (the user's history);
# <holiday dir>: <name>.JPG, the camera JPEG the tiles are picked on
#   (holiday.pick_tiles, as workflow.py; a missing JPEG falls back to the
#   nocs render, recorded as tiles_from in the metrics). No names: the five
#   workflow images.
# needs a build with csmask.patch (DT_CS_DUMP prints the "capture mask"
#   line; the <file>.Y.pfm that newer builds also write is deleted).
# Per image, in <workdir>/<name>/ (DT_DN_* and DT_CS_* are unset):
#   the demosaic entry of the history (modversion 8, params possibly
#   'gz'-compressed) is decoded and reported; only its params change, the
#   rest of the history (denoise entry and its enabled state included) is
#   untouched. Params are written as plain hex.
#   nocs       cs_enabled 0
#   thrs_<t>   cs_enabled 1, cs_thrs t, the user's cs_radius: the user's
#              own threshold and 0.40 0.45 0.50 0.55 0.60 0.70 (no
#              duplicates). A radius of 0 would make darktable autotune it
#              only with equal basic and current history hashes, which is
#              checked and reported.
#   full-frame 16-bit uncompressed TIFF renders, two at a time, cut into
#   tiles (<version>_<tile>.png, 360x260) and deleted. DT_CS_DUMP is set on
#   the thrs_* renders: mask mean and above_half from the printed line (the
#   PFM dumps are deleted at once).
# Metrics per tile: workflow.tile_stats (fine, mid, specks, chroma) and
#   rpu_cs2's edge/flat split (classes from the nocs tile, hp RMS of L over
#   edge and flat pixels), gains relative to nocs. Per version: edge_gain
#   and flat_gain averaged over all tiles, over the flat_* tiles and over
#   the tex_* tiles; flat-tile fine luma relative to nocs (mean of the
#   per-tile ratios), flat-tile specks relative to nocs (totals).
# Output (<resultdir>): metrics.json, summary.txt, montage_<name>.jpg
#   (tex tiles and the first flat tile, center 180x130 at 2x with point
#   filter; columns nocs, the user's threshold, 0.45, 0.50, 0.55, 0.60) and
#   montage_<name>_1to1.jpg (the full tiles of the same). Finished versions
#   are skipped on rerun.
import concurrent.futures
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib
import base64

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import rpu_cs  # noqa: E402
import rpu_cs2  # noqa: E402
import workflow  # noqa: E402

NAMES = ['P1378395', 'P1378550', 'P1378607', 'P1378610', 'P1378616']
THRS = [0.40, 0.45, 0.50, 0.55, 0.60, 0.70]
MONTAGE_THRS = [0.45, 0.50, 0.55, 0.60]
FMT = '<ifiiiffffififfi'
FIELDS = ['green_eq', 'median_thrs', 'color_smoothing', 'demosaicing_method',
          'lmmse_refine', 'dual_thrs', 'cs_radius', 'cs_thrs', 'cs_boost',
          'cs_iter', 'cs_center', 'cs_enabled', 'cs_clip', 'cs_boost_freq',
          'cs_unused']
TOL = 1.05
RADIUS, THRSI, ENABLED = 6, 7, 11


def tname(t):
    return f'{t:.2f}'


# --- history ---------------------------------------------------------------
DEMOSAIC = re.compile(
    r'<rdf:li\s[^>]*?darktable:operation="demosaic"[^>]*?/>', re.S)


def decode(p):
    if p.startswith('gz'):
        return zlib.decompress(base64.b64decode(p[4:]))
    return bytes.fromhex(p)


def read_demosaic(xmp):
    x = open(xmp).read()
    li = DEMOSAIC.search(x).group(0)
    assert 'darktable:modversion="8"' in li, li
    p = re.search(r'darktable:params="([^"]+)"', li).group(1)
    b = decode(p)
    assert len(b) == struct.calcsize(FMT), len(b)
    return list(struct.unpack(FMT, b)), li, x


def write_xmp(src, out, enabled, thrs=None):
    v, li, x = read_demosaic(src)
    v[ENABLED] = 1 if enabled else 0
    if thrs is not None:
        v[THRSI] = thrs
    h = struct.pack(FMT, *v).hex()
    new = re.sub(r'darktable:params="[^"]+"', f'darktable:params="{h}"', li)
    open(out, 'w').write(x.replace(li, new, 1))


def hashes(xmp):
    x = open(xmp).read()
    return {k: re.search(rf'darktable:history_{k}_hash="([^"]*)"', x).group(1)
            if re.search(rf'darktable:history_{k}_hash="', x) else None
            for k in ('basic', 'auto', 'current')}


# --- renders ---------------------------------------------------------------
def render(raw, xmp, out, dump=None):
    # holiday.cli_render without the -d pipe; the mask line is printed
    # whenever DT_CS_DUMP is set
    env = {'DT_CS_DUMP': dump} if dump else {}
    return rpu_cs.cli_render(raw, xmp, out, env)


def process(wf, hol, work, name):
    d = os.path.join(work, name)
    os.makedirs(os.path.join(d, 'xmp'), exist_ok=True)
    raw = os.path.join(wf, f'{name}_1_default.RW2')
    src = os.path.join(wf, f'{name}_1_default.xmp')
    iso = int(holiday.run(['exiftool', '-s3', '-ISO', raw]).stdout)
    params, _, _ = read_demosaic(src)
    dem = dict(zip(FIELDS, params))
    radius, own = params[RADIUS], params[THRSI]
    user = round(own, 2)
    hs = hashes(src)
    info = {'iso': iso, 'demosaic': dem, 'hashes': hs,
            'enabled_in_history': bool(params[ENABLED]),
            'radius_zero_autotunes': (radius == 0
                                      and hs['basic'] == hs['current'])}
    ts = [user] + [t for t in THRS if abs(t - user) > 1e-6]
    ts.sort()
    versions = ['nocs'] + [f'thrs_{tname(t)}' for t in ts]
    xmps = {}
    for v in versions:
        x = os.path.join(d, 'xmp', f'{v}.xmp')
        if v == 'nocs':
            write_xmp(src, x, False)
        else:
            write_xmp(src, x, True, float(v.split('_')[1]))
        xmps[v] = x
    covf = os.path.join(d, 'coverage.json')
    cov = json.load(open(covf)) if os.path.exists(covf) else {}
    tilef = os.path.join(d, 'tiles.json')

    # tiles: camera JPEG, else the nocs render
    jpg = os.path.join(hol, name + '.JPG')
    if os.path.exists(tilef):
        tiles = {k: tuple(v) for k, v in json.load(open(tilef)).items()}
        tiles_from = 'cached'
    elif os.path.exists(jpg):
        tiles, tiles_from = holiday.pick_tiles(jpg), 'camera JPEG'
    else:
        tiles, tiles_from = None, 'nocs render (no JPEG)'
    nocs_tif = None
    if tiles is None:
        nocs_tif = os.path.join(d, 'nocs.tif')
        render(raw, xmps['nocs'], nocs_tif)
        tiles = holiday.pick_tiles(nocs_tif)
    json.dump(tiles, open(tilef, 'w'))

    def png(v, t):
        return os.path.join(d, f'{v}_{t}.png')

    def one(v):
        if all(os.path.exists(png(v, t)) for t in tiles) and (
                v == 'nocs' or v in cov):
            return
        out = nocs_tif if v == 'nocs' and nocs_tif else \
            os.path.join(d, f'{v}.tif')
        dump = None if v == 'nocs' else os.path.join(d, f'mask_{v}.pfm')
        if not (v == 'nocs' and nocs_tif):
            text = render(raw, xmps[v], out, dump)
        for t, (x, y) in tiles.items():
            holiday.cut(out, x, y, png(v, t))
        os.remove(out)
        if dump:
            m = rpu_cs.parse_mask(text)
            cov[v] = {k: m[k] for k in ('thrs', 'radius', 'mean',
                                       'above_half')}
            for sfx in ('', '.Y.pfm'):
                if os.path.exists(dump + sfx):
                    os.remove(dump + sfx)
            json.dump(cov, open(covf, 'w'), indent=1)

    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        list(ex.map(one, versions))

    # metrics
    stats, rms = {}, {v: {} for v in versions}
    for t in tiles:
        edge, flat = rpu_cs2.classes(rpu_cs2.load_L(png('nocs', t)))
        for v in versions:
            stats.setdefault(v, {})[t] = workflow.tile_stats(png(v, t))
            rms[v][t] = rpu_cs2.hp_rms(rpu_cs2.load_L(png(v, t)), edge, flat)

    def avg(v, kinds, i):
        r = [rms[v][t][i] / rms['nocs'][t][i] for t in tiles
             if t.split('_')[0] in kinds]
        return sum(r) / len(r)

    def fine(v):
        r = [stats[v][t]['fine'] / stats['nocs'][t]['fine'] for t in tiles
             if t.startswith('flat')]
        return sum(r) / len(r)

    def specks(v):
        tot = lambda n: sum(stats[n][t]['specks'] for t in tiles
                            if t.startswith('flat'))
        return tot(v), tot('nocs')

    gains = {}
    for v in versions:
        g = {}
        for lab, kinds in (('all', ('flat', 'tex')), ('flat', ('flat',)),
                           ('tex', ('tex',))):
            g[lab] = {'edge': avg(v, kinds, 0), 'flat': avg(v, kinds, 1)}
        g['flat_fine_rel'] = fine(v)
        g['flat_specks'], g['flat_specks_nocs'] = specks(v)
        gains[v] = g
    res = {'name': name, 'iso': iso, 'info': info, 'user_thrs': user,
           'tiles': tiles, 'tiles_from': tiles_from, 'versions': versions,
           'mask': cov, 'stats': stats, 'rms': rms, 'gains': gains}
    return res


# --- montages --------------------------------------------------------------
def montage(res, d, out, out1):
    user = res['user_thrs']
    cols = [('nocs', 'no capture sharpening'),
            (f'thrs_{tname(user)}', f'your setting ({tname(user)})')]
    cols += [(f'thrs_{tname(t)}', f'threshold {tname(t)}')
             for t in MONTAGE_THRS if abs(t - user) > 1e-6]
    rows = [t for t in res['tiles'] if t.startswith('tex')] + \
        [t for t in res['tiles'] if t.startswith('flat')][:1]
    for full, o in ((False, out), (True, out1)):
        cells = []
        for t in rows:
            for v, cap in cols:
                p = os.path.join(d, f'{v}_{t}.png')
                if not full:
                    z = os.path.join(d, f'zoom_{v}_{t}.png')
                    holiday.run(['convert', '-quiet', p, '-crop',
                                 '180x130+90+65', '+repage', '-filter',
                                 'point', '-resize', '200%', z])
                    p = z
                cells += ['-label', f'{cap} {t}', p]
        holiday.run(['montage', *cells, '-tile', f'{len(cols)}x',
                     '-geometry', '+3+3', '-pointsize', '14', '-quality',
                     '90', o])
    for t in rows:
        for v, _ in cols:
            z = os.path.join(d, f'zoom_{v}_{t}.png')
            if os.path.exists(z):
                os.remove(z)


# --- summary ---------------------------------------------------------------
def summarize(results):
    L = []
    for r in results:
        dm, g = r['info']['demosaic'], r['gains']
        L.append(f"{r['name']}  ISO {r['iso']}  demosaic method "
                 f"{dm['demosaicing_method']} (LMMSE=6)  cs_radius "
                 f"{dm['cs_radius']:.3f}  user cs_thrs {r['user_thrs']:.2f}"
                 f"  cs_enabled {dm['cs_enabled']}  tiles "
                 f"{','.join(r['tiles'])} from {r['tiles_from']}")
        L.append(f"   history hashes: {r['info']['hashes']}")
        L.append('   gains relative to nocs; flat_fine = fine luma of the '
                 'flat tiles relative to nocs; specks = flat-tile specks '
                 'relative to nocs (nocs total in brackets)')
        L.append('   thrs     mask_mean above_half edge_gain flat_gain '
                 'flat_fine  specks        | flat tiles: edge flat | tex '
                 'tiles: edge flat')
        rows = []
        n0 = g['nocs']['flat_specks_nocs']
        for v in r['versions']:
            if v == 'nocs':
                continue
            t = float(v.split('_')[1])
            m, x = r['mask'][v], g[v]
            sp = f"{x['flat_specks'] / n0:.2f}" if n0 else \
                f"n/a ({x['flat_specks']})"
            lab = tname(t) + ('*' if abs(t - r['user_thrs']) < 1e-6 else '')
            L.append(f"   {lab:<8} {m['mean']:9.4f} {m['above_half']:10.4f}"
                     f" {x['all']['edge']:9.3f} {x['all']['flat']:9.3f}"
                     f" {x['flat_fine_rel']:9.3f}  {sp:<13}"
                     f"|  {x['flat']['edge']:9.3f} {x['flat']['flat']:5.3f}"
                     f" |  {x['tex']['edge']:9.3f} {x['tex']['flat']:5.3f}")
            rows.append((t, x['all']['edge'], x['all']['flat']))
        L.append(f'   (* = the user\'s threshold; nocs flat-tile specks '
                 f'total {n0})')
        ok = [x for x in rows if x[2] <= TOL]
        if ok:
            b = max(ok, key=lambda x: x[1])
            L.append(f'   best edge_gain with flat_gain <= {TOL}: thrs '
                     f'{b[0]:.2f}  edge_gain {b[1]:.3f}  flat_gain '
                     f'{b[2]:.3f}')
        else:
            L.append(f'   no threshold with flat_gain <= {TOL}')
        u = [x for x in rows if abs(x[0] - r['user_thrs']) < 1e-6][0]
        L.append(f"   user's {u[0]:.2f}: edge_gain {u[1]:.3f}  flat_gain "
                 f"{u[2]:.3f}")
        L.append('')
    return '\n'.join(L)


def main():
    wf, hol, work, resdir = sys.argv[1:5]
    names = sys.argv[5:] or NAMES
    for k in [k for k in os.environ
              if k.startswith('DT_DN_') or k.startswith('DT_CS_')]:
        del os.environ[k]
    os.makedirs(work, exist_ok=True)
    os.makedirs(resdir, exist_ok=True)
    results = []
    for n in names:
        res = process(wf, hol, work, n)
        montage(res, os.path.join(work, n),
                os.path.join(resdir, f'montage_{n}.jpg'),
                os.path.join(resdir, f'montage_{n}_1to1.jpg'))
        results.append(res)
        print(n, 'done', flush=True)
    json.dump({r['name']: r for r in results},
              open(os.path.join(resdir, 'metrics.json'), 'w'), indent=1)
    s = summarize(results)
    open(os.path.join(resdir, 'summary.txt'), 'w').write(s)
    print(s)


if __name__ == '__main__':
    main()
