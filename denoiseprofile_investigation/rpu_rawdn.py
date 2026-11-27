# task rawdn: the user's own histories (workflow dir) with raw denoise added
# to the history, combined with capture sharpening thresholds, to see whether
# raw denoise lets capture sharpening keep its edge gain without lifting the
# flat-area noise.
#
#   BUILD=<build> python3 rpu_rawdn.py <workflow dir> <holiday dir> <workdir> \
#       <resultdir> <cswf metrics.json> [<name>...]
#
# builds on rpu_cswf.py (imported, not modified): its demosaic-entry
# decoding and params writer, tile cutting and the edge/flat metric via
# rpu_cs2 and workflow.tile_stats. Needs a build with csmask.patch
# (DT_CS_DUMP).
# <cswf metrics.json>: the tile coordinates of the cswf task are reused (so
#   the tiles are the ones of that session); an image missing from it gets
#   tiles picked on <holiday dir>/<name>.JPG as in cswf.
# Per image, in <workdir>/<name>/ (DT_DN_* and DT_CS_* are unset except
# DT_CS_DUMP on the renders with capture sharpening, whose PFMs are deleted
# at once); the rest of the user's history, including its denoise (profiled)
# entry, is untouched:
#   nocs                capture sharpening disabled, no raw denoise
#   rd<T>_cs<C>         raw denoise threshold T (or 'off': no history
#                       entry), capture sharpening threshold C and the
#                       user's radius; T in RD_T, C in CS_C
#   rd0.02_nocs         raw denoise 0.02 without capture sharpening
#   Raw denoise is a 'rawdenoise' entry (modversion 2, params as
#   variants_xmp.rawdenoise(): all curve points flat at 0.5) appended to the
#   history with the next num; history_end is raised by one. On the
#   rd0.02_cs0.33 render -d pipe is on and the process list is checked for
#   rawdenoise running before demosaic (pipe_<name>.log, 'pipe_check' in the
#   metrics).
#   Full-frame 16-bit uncompressed TIFF renders, two at a time, cut into
#   360x260 tiles and deleted.
# References: <workflow dir>/export/<name>_2_neural_50.tif and
#   <name>_3_topaz.tif (the user's Windows build, not rendered here) are cut
#   at the same coordinates and measured like the versions.
# Metrics per tile as in cswf (tile_stats, rpu_cs2 edge/flat RMS with the
#   classes from the nocs tile); per version, relative to nocs: edge_gain,
#   flat_gain (all tiles), flat-tile fine luma (mean of per-tile ratios),
#   tex-tile mid luma (same), specks (flat-tile and all-tile totals), mask
#   mean.
# Output (<resultdir>): metrics.json, summary.txt, montage_<name>.jpg
import concurrent.futures
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import rpu_cs  # noqa: E402
import rpu_cs2  # noqa: E402
import rpu_cswf  # noqa: E402
import workflow  # noqa: E402

NAMES = ['P1378607', 'P1378616', 'P1378610']
RD_T = ['off', 0.005, 0.01, 0.02, 0.03]
CS_C = [0.33, 0.55]
TOL = 1.05
EXPORTS = [('neural50', '_2_neural_50.tif', 'neural 50 (export)'),
           ('topaz', '_3_topaz.tif', 'Topaz (export)')]
BLEND = 'gz10eJxjYGBgYAZiCQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAG9SHQg='
END = '    </rdf:Seq>\n   </darktable:history>'
PIPE_REF = 'rd0.02_cs0.33'
MONTAGE = [('nocs', 'no capture sharpening'),
           ('rdoff_cs0.33', 'no raw denoise, cs 0.33 (yours)'),
           ('rdoff_cs0.55', 'no raw denoise, cs 0.55'),
           ('rd0.01_cs0.33', 'raw denoise 0.01, cs 0.33'),
           ('rd0.02_cs0.33', 'raw denoise 0.02, cs 0.33'),
           ('rd0.03_cs0.33', 'raw denoise 0.03, cs 0.33'),
           ('rd0.02_cs0.55', 'raw denoise 0.02, cs 0.55'),
           ('neural50', 'neural 50 (export)'),
           ('topaz', 'Topaz (export)')]


def tstr(t):
    return t if t == 'off' else f'{t:g}'


def vname(t, c):
    return f'rd{tstr(t)}_cs{c:g}' if c is not None else f'rd{tstr(t)}_nocs'


def rawdenoise(threshold):
    # holiday's variants_xmp.rawdenoise(): dt_iop_rawdenoise_params_t v2
    b = struct.pack('<f', threshold)
    b += struct.pack('<20f', *([k / 4.0 for k in range(5)] * 4))
    b += struct.pack('<20f', *([0.5] * 20))
    return b.hex()


def write_xmp(src, out, thrs, rd):
    # thrs None: capture sharpening off; rd None: no raw denoise entry
    rpu_cswf.write_xmp(src, out, thrs is not None, thrs)
    if rd is None:
        return
    x = open(out).read()
    n0 = int(re.search(r'darktable:history_end="(\d+)"', x).group(1))
    nums = [int(n) for n in re.findall(r'darktable:num="(\d+)"', x)]
    assert n0 == max(nums) + 1, (n0, nums)
    li = (f'     <rdf:li darktable:num="{n0}"'
          f' darktable:operation="rawdenoise" darktable:enabled="1"\n'
          f'      darktable:modversion="2" darktable:params="'
          f'{rawdenoise(rd)}" darktable:multi_name=""'
          f' darktable:multi_priority="0"\n'
          f'      darktable:blendop_version="15"'
          f' darktable:blendop_params="{BLEND}"/>\n')
    assert END in x and 'operation="rawdenoise"' not in x
    x = x.replace(END, li + END, 1).replace(
        f'history_end="{n0}"', f'history_end="{n0 + 1}"')
    open(out, 'w').write(x)


def pipe_check(text):
    # the "process" lines list the modules in the order they run
    names = []
    for l in text.splitlines():
        m = re.match(r'\s*[\d.]+\s+process\s+(CPU|GPU)\s+\[\w+\]\s+(\w+)', l)
        if m:
            names.append(m.group(2))
    r = {'process_order': names,
         'rawdenoise_runs': 'rawdenoise' in names,
         'before_demosaic': ('rawdenoise' in names and 'demosaic' in names
                             and names.index('rawdenoise') <
                             names.index('demosaic'))}
    return r


def process(wf, hol, work, name, cswf_tiles):
    d = os.path.join(work, name)
    os.makedirs(os.path.join(d, 'xmp'), exist_ok=True)
    raw = os.path.join(wf, f'{name}_1_default.RW2')
    src = os.path.join(wf, f'{name}_1_default.xmp')
    iso = int(holiday.run(['exiftool', '-s3', '-ISO', raw]).stdout)
    params, _, _ = rpu_cswf.read_demosaic(src)
    dem = dict(zip(rpu_cswf.FIELDS, params))
    info = {'iso': iso, 'demosaic': dem, 'hashes': rpu_cswf.hashes(src),
            'user_thrs': round(params[rpu_cswf.THRSI], 2)}
    assert abs(info['user_thrs'] - 0.33) < 1e-6, info['user_thrs']

    # versions: name -> (cs threshold or None, raw denoise or None)
    spec = {'nocs': (None, None)}
    for c in CS_C:
        for t in RD_T:
            spec[vname(t, c)] = (c, None if t == 'off' else t)
    spec['rd0.02_nocs'] = (None, 0.02)
    xmps = {}
    for v, (c, t) in spec.items():
        xmps[v] = os.path.join(d, 'xmp', f'{v}.xmp')
        write_xmp(src, xmps[v], c, t)
    covf = os.path.join(d, 'coverage.json')
    cov = json.load(open(covf)) if os.path.exists(covf) else {}
    pipef = os.path.join(d, 'pipe_check.json')

    jpg = os.path.join(hol, name + '.JPG')
    if name in cswf_tiles:
        tiles, tiles_from = cswf_tiles[name], 'cswf metrics.json'
    else:
        tiles, tiles_from = holiday.pick_tiles(jpg), 'camera JPEG'
    json.dump(tiles, open(os.path.join(d, 'tiles.json'), 'w'))

    def png(v, t):
        return os.path.join(d, f'{v}_{t}.png')

    def one(v):
        c, t = spec[v]
        if all(os.path.exists(png(v, k)) for k in tiles) and (
                c is None or v in cov) and (v != PIPE_REF
                                            or os.path.exists(pipef)):
            return
        out = os.path.join(d, f'{v}.tif')
        dump = os.path.join(d, f'mask_{v}.pfm') if c is not None else None
        env = {'DT_CS_DUMP': dump} if dump else {}
        text = rpu_cs.cli_render(raw, xmps[v], out, env, debug=(v == PIPE_REF))
        for k, (x, y) in tiles.items():
            holiday.cut(out, x, y, png(v, k))
        os.remove(out)
        if v == PIPE_REF:
            open(os.path.join(d, f'pipe_{v}.log'), 'w').write(text)
            json.dump(pipe_check(text), open(pipef, 'w'), indent=1)
        if dump:
            m = rpu_cs.parse_mask(text)
            cov[v] = {k: m[k] for k in ('thrs', 'radius', 'mean',
                                       'above_half')}
            for sfx in ('', '.Y.pfm'):
                if os.path.exists(dump + sfx):
                    os.remove(dump + sfx)
            json.dump(cov, open(covf, 'w'), indent=1)

    versions = list(spec)
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        list(ex.map(one, versions))
    # exports: cut at the same coordinates
    exp_labels = {}
    for v, sfx, lab in EXPORTS:
        f = os.path.join(wf, 'export', name + sfx)
        exp_labels[v] = lab
        if not os.path.exists(f):
            continue
        if not all(os.path.exists(png(v, k)) for k in tiles):
            for k, (x, y) in tiles.items():
                holiday.cut(f, x, y, png(v, k))
        versions.append(v)

    stats, rms = {}, {v: {} for v in versions}
    for k in tiles:
        edge, flat = rpu_cs2.classes(rpu_cs2.load_L(png('nocs', k)))
        for v in versions:
            stats.setdefault(v, {})[k] = workflow.tile_stats(png(v, k))
            rms[v][k] = rpu_cs2.hp_rms(rpu_cs2.load_L(png(v, k)), edge, flat)

    def mean(xs):
        return sum(xs) / len(xs)

    gains = {}
    for v in versions:
        g = {'edge_gain': mean([rms[v][k][0] / rms['nocs'][k][0]
                                for k in tiles]),
             'flat_gain': mean([rms[v][k][1] / rms['nocs'][k][1]
                                for k in tiles]),
             'flat_fine_rel': mean([stats[v][k]['fine']
                                    / stats['nocs'][k]['fine']
                                    for k in tiles if k.startswith('flat')]),
             'tex_mid_rel': mean([stats[v][k]['mid'] / stats['nocs'][k]['mid']
                                  for k in tiles if k.startswith('tex')])}
        for lab, pre in (('flat', 'flat'), ('all', '')):
            tot = sum(stats[v][k]['specks'] for k in tiles
                      if k.startswith(pre))
            tot0 = sum(stats['nocs'][k]['specks'] for k in tiles
                       if k.startswith(pre))
            g[f'specks_{lab}'] = tot
            g[f'specks_{lab}_nocs'] = tot0
        g['mask_mean'] = cov[v]['mean'] if v in cov else None
        gains[v] = g
    return {'name': name, 'iso': iso, 'info': info, 'tiles': tiles,
            'tiles_from': tiles_from, 'versions': versions,
            'labels': exp_labels, 'mask': cov, 'stats': stats, 'rms': rms,
            'gains': gains, 'pipe_check': json.load(open(pipef))}


# --- montage ----------------------------------------------------------------
def montage(res, d, out):
    cols = [(v, cap) for v, cap in MONTAGE if v in res['versions']]
    rows = ['tex_0', 'tex_1', 'flat_0']
    cells, zooms = [], []
    for t in rows:
        for v, cap in cols:
            z = os.path.join(d, f'zoom_{v}_{t}.png')
            holiday.run(['convert', '-quiet', os.path.join(d, f'{v}_{t}.png'),
                         '-crop', '180x130+90+65', '+repage', '-filter',
                         'point', '-resize', '200%', z])
            zooms.append(z)
            cells += ['-label', f'{cap} | {t}', z]
    holiday.run(['montage', *cells, '-tile', f'{len(cols)}x', '-geometry',
                 '+3+3', '-pointsize', '13', '-quality', '90', out])
    for z in zooms:
        os.remove(z)


# --- summary ----------------------------------------------------------------
def rows_of(r):
    return [v for v in r['versions']]


def summarize(results):
    L = []
    for r in results:
        g, pc = r['gains'], r['pipe_check']
        L.append(f"{r['name']}  ISO {r['iso']}  cs_radius "
                 f"{r['info']['demosaic']['cs_radius']:.3f}  user cs_thrs "
                 f"{r['info']['user_thrs']:.2f}  tiles "
                 f"{','.join(r['tiles'])} from {r['tiles_from']}")
        L.append(f"   pipe check on {PIPE_REF}: rawdenoise runs "
                 f"{pc['rawdenoise_runs']}, before demosaic "
                 f"{pc['before_demosaic']}")
        L.append('   all gains relative to nocs (mean over the 4 tiles for '
                 'edge/flat gain). flat_fine: fine luma of the flat tiles; '
                 'tex_mid: mid luma of the tex tiles (mean of per-tile '
                 'ratios); specks: flat-tile total / all-tile total relative '
                 'to nocs (nocs totals in brackets).')
        L.append('   version            mask_mean edge_gain flat_gain '
                 'flat_fine tex_mid  specks_flat  specks_all')
        n0f = g['nocs']['specks_flat_nocs']
        n0a = g['nocs']['specks_all_nocs']
        for v in rows_of(r):
            x = g[v]
            lab = r['labels'].get(v, v)
            mm = f"{x['mask_mean']:.4f}" if x['mask_mean'] is not None \
                else '   -   '
            sf = f"{x['specks_flat'] / n0f:.2f}" if n0f else \
                f"n/a({x['specks_flat']})"
            sa = f"{x['specks_all'] / n0a:.2f}" if n0a else \
                f"n/a({x['specks_all']})"
            L.append(f"   {lab:<24} {mm:>7} {x['edge_gain']:9.3f} "
                     f"{x['flat_gain']:9.3f} {x['flat_fine_rel']:9.3f} "
                     f"{x['tex_mid_rel']:7.3f}  {sf:>10}  {sa:>10}")
        L.append(f'   (nocs specks totals: flat tiles {n0f}, all tiles '
                 f'{n0a})')
        ok = [v for v in r['versions'] if v != 'nocs'
              and g[v]['flat_gain'] <= TOL]
        L.append(f'   versions with flat_gain <= {TOL}: '
                 + (', '.join(f"{r['labels'].get(v, v)} "
                              f"(flat {g[v]['flat_gain']:.3f}, edge "
                              f"{g[v]['edge_gain']:.3f})" for v in ok)
                    or 'none'))
        if ok:
            b = max(ok, key=lambda v: g[v]['edge_gain'])
            L.append(f"   highest edge_gain among them: "
                     f"{r['labels'].get(b, b)}  edge_gain "
                     f"{g[b]['edge_gain']:.3f}  flat_gain "
                     f"{g[b]['flat_gain']:.3f}")
        ok2 = [v for v in ok if v not in r['labels']]
        if ok2:
            b = max(ok2, key=lambda v: g[v]['edge_gain'])
            L.append(f"   same, rendered versions only: {b}  edge_gain "
                     f"{g[b]['edge_gain']:.3f}")
        # rdoff_cs0.55 against the best rd<T>_cs0.33 (raw denoise on):
        # highest edge_gain with flat_gain <= TOL, else the lowest flat_gain
        cand = [v for v in r['versions'] if re.fullmatch(
            r'rd[0-9.]+_cs0\.33', v)]
        okc = [v for v in cand if g[v]['flat_gain'] <= TOL]
        if okc:
            best = max(okc, key=lambda v: g[v]['edge_gain'])
            how = 'highest edge_gain with flat_gain <= %.2f' % TOL
        else:
            best = min(cand, key=lambda v: g[v]['flat_gain'])
            how = 'none within %.2f; lowest flat_gain' % TOL
        a, b = g['rdoff_cs0.55'], g[best]
        L.append(f"   rdoff_cs0.55 vs best rd*_cs0.33 ({best}; {how}):")
        L.append(f"      rdoff_cs0.55  edge {a['edge_gain']:.3f}  flat "
                 f"{a['flat_gain']:.3f}  flat_fine {a['flat_fine_rel']:.3f}"
                 f"  tex_mid {a['tex_mid_rel']:.3f}")
        L.append(f"      {best:<13} edge {b['edge_gain']:.3f}  flat "
                 f"{b['flat_gain']:.3f}  flat_fine {b['flat_fine_rel']:.3f}"
                 f"  tex_mid {b['tex_mid_rel']:.3f}")
        L.append('')
    return '\n'.join(L)


def main():
    wf, hol, work, resdir, cswf = sys.argv[1:6]
    names = sys.argv[6:] or NAMES
    for k in [k for k in os.environ
              if k.startswith('DT_DN_') or k.startswith('DT_CS_')]:
        del os.environ[k]
    os.makedirs(work, exist_ok=True)
    os.makedirs(resdir, exist_ok=True)
    cswf_tiles = {n: {k: tuple(v) for k, v in r['tiles'].items()}
                  for n, r in json.load(open(cswf)).items()}
    results = []
    for n in names:
        res = process(wf, hol, work, n, cswf_tiles)
        montage(res, os.path.join(work, n),
                os.path.join(resdir, f'montage_{n}.jpg'))
        results.append(res)
        print(n, 'done', flush=True)
    json.dump({r['name']: r for r in results},
              open(os.path.join(resdir, 'metrics.json'), 'w'), indent=1)
    s = summarize(results)
    open(os.path.join(resdir, 'summary.txt'), 'w').write(s)
    print(s)


if __name__ == '__main__':
    main()
