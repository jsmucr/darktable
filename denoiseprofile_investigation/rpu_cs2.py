# task cs2: follow-up to rpu_cs.py. Finer capture sharpening threshold sweep
# (thrs_auto, 0.40 .. 0.60 in steps of 0.05, plus 0.65, 0.70, 0.75 for
# Canon_EOS_R50), each with denoise (profiled) off and with its defaults,
# and an edge/flat gain metric that separates "sharpening real edges" from
# "sharpening noise in flat areas".
#
#   BUILD=<build> python3 rpu_cs2.py <csdir> <rawdir> <picked.json> \
#       <workdir> <resultdir> [<tag>...]
#
# <csdir>: rpu_cs.py results (<tag>_metrics.json: tiles, auto thrs and
#   radius, a); the tiles and the pinned radius_auto are taken from there.
# <rawdir>/<tag>.<ext>, <picked.json>: as rpu_cs.py (extension from the raw
#   url); Panasonic_DC_G9_P1378616 is /c/temp/denoise/P1378616.RW2.
# needs a build with csmask.patch (DT_CS_DUMP; the <file>.Y.pfm that newer
#   builds also write is deleted).
# Per image, in <workdir>/<tag>/: for none, ship and every threshold (radius
#   pinned to radius_auto) a full render, cut into tiles
#   (<version>_<tile>.png, 360x260) and deleted; two renders at a time.
#   Version names: none, ship, cs_auto_<off|dn>, cs_<t>_<off|dn> (t as
#   0.40; a threshold equal to thrs_auto is not rendered twice).
#   mask coverage (mean, above_half) from the DT_CS_DUMP of the *_off renders
# metric (pure python): L of each tile (Lab, 16 bit /65535); pixels
#   classified from the 'ship' tile: 3x3 box blur, gradient |dx|+|dy| by
#   central differences, edge = top 15% by gradient, flat = bottom 50%
#   (pixels 2..W-3, 2..H-3 only, the same classes for every version);
#   high-pass of L = L - 3x3 box mean; RMS of it over the edge and over the
#   flat pixels; edge_gain = edge RMS(version) / edge RMS(reference),
#   flat_gain likewise, reference none for denoise off and ship for on;
#   averaged over all tiles of the image.
# Output: <resultdir>/<tag>_metrics2.json, <tag>_montage2.jpg (tex tiles
#   only, 2x crop of the center 180x130), summary2.txt.
import concurrent.futures
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import rpu_cs  # noqa: E402
import rpu_wbexp  # noqa: E402
import y0fix  # noqa: E402

TW, TH = holiday.TW, holiday.TH
THRS = [0.40, 0.45, 0.50, 0.55, 0.60]
THRS_R50 = THRS + [0.65, 0.70, 0.75]
TOL = 1.05
MONTAGE = ['none', 'cs_auto_off', 'cs_0.45_off', 'cs_0.50_off',
           'cs_0.55_off', 'ship', 'cs_auto_dn', 'cs_0.50_dn']
P1378616_TAG = rpu_cs.P1378616_TAG
TAGS = ['Sony_ILCE_7C', 'Canon_EOS_M3', 'Canon_EOS_77D', 'Nikon_1_J5',
        'Fujifilm_X70', 'Fujifilm_X_T10', 'Canon_EOS_R50', P1378616_TAG]


def tname(t):
    return f'{t:.2f}'


def versions(auto, tag):
    # [(version, threshold value or None, denoise on)], thresholds in
    # ascending order, a threshold equal to thrs_auto only as 'auto'
    out = [('none', None, False), ('ship', None, True)]
    ts = [('auto', auto)] + [(tname(t), t) for t in
                             (THRS_R50 if tag == 'Canon_EOS_R50' else THRS)
                             if abs(t - auto) > 1e-6]
    ts.sort(key=lambda x: x[1])
    for name, t in ts:
        out += [(f'cs_{name}_off', t, False), (f'cs_{name}_dn', t, True)]
    return out


# --- metric ----------------------------------------------------------------
def load_L(path):
    p = subprocess.run(['convert', '-quiet', path, '-colorspace', 'Lab',
                        '-channel', 'R', '-separate', '+channel', '-depth',
                        '16', '-endian', 'LSB', 'gray:-'],
                       check=True, capture_output=True)
    n = len(p.stdout) // 2
    assert n == TW * TH, (path, n)
    import array
    a = array.array('H')
    a.frombytes(p.stdout)
    return [v / 65535 for v in a]


def box3(v):
    # 3x3 box mean at interior pixels 1..W-2, 1..H-2 (others 0)
    w, h = TW, TH
    hs = [0.0] * (w * h)
    for y in range(h):
        o = y * w
        for x in range(1, w - 1):
            hs[o + x] = v[o + x - 1] + v[o + x] + v[o + x + 1]
    out = [0.0] * (w * h)
    for y in range(1, h - 1):
        o = y * w
        for x in range(1, w - 1):
            out[o + x] = (hs[o - w + x] + hs[o + x] + hs[o + w + x]) / 9
    return out


def classes(ship):
    # edge and flat pixel indices from the ship tile
    w, h = TW, TH
    b = box3(ship)
    idx, g = [], []
    for y in range(2, h - 2):
        for x in range(2, w - 2):
            i = y * w + x
            idx.append(i)
            g.append(abs(b[i + 1] - b[i - 1]) + abs(b[i + w] - b[i - w]))
    order = sorted(range(len(idx)), key=g.__getitem__)
    n = len(order)
    flat = [idx[k] for k in order[:n // 2]]
    edge = [idx[k] for k in order[n - int(round(0.15 * n)):]]
    return edge, flat


def hp_rms(L, edge, flat):
    b = box3(L)
    f = lambda s: math.sqrt(sum((L[i] - b[i]) ** 2 for i in s) / len(s))
    return f(edge), f(flat)


def tile_rms(d, versions_, tiles):
    # {version: {tile: [edge rms, flat rms]}}
    res = {v: {} for v in versions_}
    for t in tiles:
        edge, flat = classes(load_L(os.path.join(d, f'ship_{t}.png')))
        for v in versions_:
            res[v][t] = hp_rms(load_L(os.path.join(d, f'{v}_{t}.png')),
                               edge, flat)
    return res


def gains(rms, v, ref):
    e = [rms[v][t][0] / rms[ref][t][0] for t in rms[v]]
    f = [rms[v][t][1] / rms[ref][t][1] for t in rms[v]]
    return sum(e) / len(e), sum(f) / len(f)


# --- renders ---------------------------------------------------------------
def process(tag, r, raw, work, csdir):
    d = os.path.join(work, tag)
    os.makedirs(d, exist_ok=True)
    cs = json.load(open(os.path.join(csdir, f'{tag}_metrics.json')))
    tiles = {k: tuple(v) for k, v in cs['tiles'].items()}
    a = cs['a']
    radius, auto = cs['auto']['radius'], cs['auto']['thrs']
    vs = versions(auto, tag)
    covf = os.path.join(d, 'coverage.json')
    cov = json.load(open(covf)) if os.path.exists(covf) else {}

    def one(item):
        v, thrs, dn = item
        tilepng = lambda t: os.path.join(d, f'{v}_{t}.png')
        if all(os.path.exists(tilepng(t)) for t in tiles) and (
                dn or v == 'none' or v in cov):
            return
        env, items = {}, []
        if v.startswith('cs_'):
            items.append(('demosaic', 8, rpu_cs.demosaic(radius, thrs), 1))
            if not dn:
                env['DT_CS_DUMP'] = os.path.join(d, f'mask_{v}.pfm')
        items.append(('denoiseprofile', 12, y0fix.default_params(a),
                      int(dn)))
        x = os.path.join(d, f'{v}.xmp')
        rpu_wbexp.xmp(x, items)
        out = os.path.join(d, f'{v}.tif')
        text = rpu_cs.cli_render(raw, x, out, env)
        for t, (tx, ty) in tiles.items():
            holiday.cut(out, tx, ty, tilepng(t))
        os.remove(out)
        if 'DT_CS_DUMP' in env:
            m = rpu_cs.parse_mask(text)
            cov[v] = {k: m[k] for k in ('thrs', 'radius', 'mean',
                                       'above_half')}
            for suffix in ('', '.Y.pfm'):
                if os.path.exists(env['DT_CS_DUMP'] + suffix):
                    os.remove(env['DT_CS_DUMP'] + suffix)
            json.dump(cov, open(covf, 'w'), indent=1)

    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        list(ex.map(one, vs))
    names = [v for v, _, _ in vs]
    rms = tile_rms(d, names, tiles)
    res = {'tag': tag, 'sample': r, 'tiles': tiles, 'radius': radius,
           'thrs_auto': auto, 'rms': rms, 'mask': cov, 'versions': [
               [v, t, dn] for v, t, dn in vs],
           'sanity_none': gains(rms, 'none', 'none')}
    res['gains'] = {}
    for v, t, dn in vs:
        if v in ('none', 'ship'):
            continue
        res['gains'][v] = gains(rms, v, 'ship' if dn else 'none')
    return res


# --- montage ---------------------------------------------------------------
def montage(res, d, out):
    auto = res['thrs_auto']
    have = {v for v, _, _ in res['versions']}
    cells = []
    tex = [t for t in res['tiles'] if t.startswith('tex')]
    for t in tex:
        for v in MONTAGE:
            if v not in have:
                continue
            m = re.match(r'cs_(.+)_(off|dn)$', v)
            if m:
                th = auto if m.group(1) == 'auto' else float(m.group(1))
                cap = f'{v} thrs={th:.2f}'
            else:
                cap = f'{v} (no sharpening)'
            tmp = os.path.join(d, f'zoom_{v}_{t}.png')
            holiday.run(['convert', '-quiet', os.path.join(d, f'{v}_{t}.png'),
                         '-crop', '180x130+90+65', '+repage', '-filter',
                         'point', '-resize', '200%', tmp])
            cells += ['-label', f'{cap} {t}', tmp]
    holiday.run(['montage', *cells, '-tile',
                 f'{sum(v in have for v in MONTAGE)}x', '-geometry', '+3+3',
                 '-pointsize', '14', '-quality', '90', out])
    for t in tex:
        for v in MONTAGE:
            p = os.path.join(d, f'zoom_{v}_{t}.png')
            if os.path.exists(p):
                os.remove(p)


# --- summary ---------------------------------------------------------------
def summarize(results):
    L = []
    for r in results:
        if r is None:
            continue
        tag, auto = r['tag'], r['thrs_auto']
        L.append(f"{tag}  ISO {r['sample']['iso']}  thrs_auto {auto:.2f}  "
                 f"radius_auto {r['radius']:.3f}  tiles "
                 f"{','.join(r['tiles'])}")
        e, f = r['sanity_none']
        L.append(f'   sanity none vs none: edge_gain {e:.3f} flat_gain '
                 f'{f:.3f}')
        for sfx, ref in (('off', 'none'), ('dn', 'ship')):
            L.append(f'   denoise {"off" if sfx == "off" else "on"} '
                     f'(reference {ref}):')
            L.append('     thrs     mask_mean  above_half  edge_gain  '
                     'flat_gain')
            rows = []
            for v, t, dn in r['versions']:
                m = re.match(rf'cs_(.+)_{sfx}$', v)
                if not m:
                    continue
                mk = r['mask'][f'cs_{m.group(1)}_off']
                eg, fg = r['gains'][v]
                lab = f'{t:.2f}' + (' (auto)' if m.group(1) == 'auto'
                                    else '')
                rows.append((v, t, eg, fg))
                L.append(f'     {lab:<8} {mk["mean"]:9.4f}  '
                         f'{mk["above_half"]:10.4f}  {eg:9.3f}  {fg:9.3f}')
            ok = [x for x in rows if x[3] <= TOL]
            if ok:
                b = max(ok, key=lambda x: x[2])
                L.append(f'     best edge_gain with flat_gain <= {TOL}: '
                         f'thrs {b[1]:.2f}  edge_gain {b[2]:.3f}  '
                         f'flat_gain {b[3]:.3f}')
            else:
                L.append(f'     no threshold with flat_gain <= {TOL}')
            au = [x for x in rows if x[0] == f'cs_auto_{sfx}'][0]
            L.append(f'     at thrs_auto {auto:.2f}: edge_gain {au[2]:.3f}  '
                     f'flat_gain {au[3]:.3f}')
        L.append('')
    return '\n'.join(L)


def main():
    csdir, rawdir, picked, work, resdir = sys.argv[1:6]
    want = set(sys.argv[6:])
    for k in [k for k in os.environ if k.startswith('DT_DN_')
              or k == 'DT_CS_DUMP']:
        del os.environ[k]
    os.makedirs(work, exist_ok=True)
    os.makedirs(resdir, exist_ok=True)
    pk = {re.sub(r'\W+', '_', f"{r['make']}_{r['model']}"): r
          for r in json.load(open(picked))}
    results = []
    for tag in TAGS:
        if tag == P1378616_TAG:
            r, raw = rpu_cs.P1378616, '/c/temp/denoise/P1378616.RW2'
        else:
            r = pk[tag]
            raw = os.path.join(rawdir, tag + os.path.splitext(r['raw'])[1])
        mf = os.path.join(resdir, f'{tag}_metrics2.json')
        if want and tag not in want:
            results.append(json.load(open(mf)) if os.path.exists(mf)
                           else None)
            continue
        try:
            res = process(tag, r, raw, work, csdir)
            json.dump(res, open(mf, 'w'), indent=1)
            montage(res, os.path.join(work, tag),
                    os.path.join(resdir, f'{tag}_montage2.jpg'))
            results.append(res)
            print(tag, 'done', flush=True)
        except (subprocess.CalledProcessError, RuntimeError) as e:
            print('failed:', tag, getattr(e, 'stderr', None) or e,
                  flush=True)
            results.append(None)
    s = summarize(results)
    open(os.path.join(resdir, 'summary2.txt'), 'w').write(s)
    print(s)


if __name__ == '__main__':
    main()
