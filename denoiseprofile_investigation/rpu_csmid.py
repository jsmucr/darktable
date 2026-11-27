# task csmid: rpu_cswf's sweep on the ISO range between the workflow
# images (ISO 800 and 6400), with the user's own history applied to
# holiday raws that have no XMP of their own.
#
#   BUILD=<build> python3 rpu_csmid.py <history xmp> <holiday dir> <workdir> \
#       <resultdir> <session metrics.json> <name>[=<raw>] ...
#
# <history xmp>: the user's XMP (P1378550_1_default.xmp, ISO 800); it is
#   copied unchanged for every image. Its lens entry names the lens, focal
#   length and aperture of that shot and is kept as is (reported).
# <name>: holiday/<name>.RW2 and, for the tiles, holiday/<name>.JPG. With
#   <name>=<raw> the raw is taken from <raw> instead and, without a JPEG
#   in <holiday dir>, the tiles come from the nocs render (tiles_from).
# <session metrics.json>: the earlier workflow sweep (rpu_cswf.py's
#   metrics.json), for the combined table.
# rpu_cswf.process does the work through a staging dir of symlinks
#   (<workdir>/stage/<name>_1_default.{RW2,xmp}); only the sweep differs:
#   nocs and thrs in {0.33 (the user's), 0.40 0.45 0.50 0.55 0.60}.
# Output (<resultdir>): metrics.json, summary.txt, montage_<name>.jpg
#   (rows tex_0 and flat_0, 180x130 centre at 2x, point filter; columns
#   nocs, 0.33, 0.45, 0.50, 0.55; captions carry the ISO).
# Summary: per image the table threshold -> mask mean, edge_gain,
#   flat_gain, flat fine (flat-tile fine luma relative to nocs), tex mid
#   (tex-tile mid luma relative to nocs) and the lowest threshold with
#   flat_gain <= 1.05 and flat fine <= 1.05; then one table of these
#   images plus the session's, sorted by ISO. "flat?" flags an image whose
#   nocs flat tile has fine-band energy of at least FLAG times the mean of
#   its tex tiles: that flat tile may be texture (or, at high ISO, noise
#   dominates both), for a human to judge on the montage.
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402
import rpu_cswf  # noqa: E402

rpu_cswf.THRS = [0.40, 0.45, 0.50, 0.55, 0.60]
MONTAGE_THRS = [0.45, 0.50, 0.55]
TOL = rpu_cswf.TOL
FLAG = 0.5
tname = rpu_cswf.tname


def stage(xmp, hol, work, specs):
    sd = os.path.join(work, 'stage')
    os.makedirs(sd, exist_ok=True)
    names = []
    for s in specs:
        name, _, raw = s.partition('=')
        raw = raw or os.path.join(hol, name + '.RW2')
        link = os.path.join(sd, f'{name}_1_default.RW2')
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(raw, link)
        with open(xmp, 'rb') as f, \
                open(os.path.join(sd, f'{name}_1_default.xmp'), 'wb') as g:
            g.write(f.read())
        names.append(name)
    return sd, names


def montage(res, d, out):
    iso = res['iso']
    user = res['user_thrs']
    cols = [('nocs', 'no capture sharpening'),
            (f'thrs_{tname(user)}', f'your setting {tname(user)}')]
    cols += [(f'thrs_{tname(t)}', f'threshold {tname(t)}')
             for t in MONTAGE_THRS]
    rows = ['tex_0', 'flat_0']
    cells, zooms = [], []
    for t in rows:
        for v, cap in cols:
            z = os.path.join(d, f'zoom_{v}_{t}.png')
            holiday.run(['convert', '-quiet', os.path.join(d, f'{v}_{t}.png'),
                         '-crop', '180x130+90+65', '+repage', '-filter',
                         'point', '-resize', '200%', z])
            zooms.append(z)
            cells += ['-label', f"{res['name']} ISO {iso}\n{cap}\n{t}", z]
    holiday.run(['montage', *cells, '-tile', f'{len(cols)}x', '-geometry',
                 '+3+3', '-pointsize', '16', '-quality', '90', out])
    for z in zooms:
        os.remove(z)


def derived(r):
    # per version (all but nocs): the numbers of the tables, and the
    # nocs flat/tex fine ratio
    st, g = r['stats'], r['gains']
    tex = [t for t in r['tiles'] if t.startswith('tex')]
    out = {}
    for v in r['versions']:
        if v == 'nocs':
            continue
        mid = [st[v][t]['mid'] / st['nocs'][t]['mid'] for t in tex]
        out[v] = {'thrs': float(v.split('_')[1]),
                  'mean': r['mask'][v]['mean'],
                  'above_half': r['mask'][v]['above_half'],
                  'edge': g[v]['all']['edge'], 'flat': g[v]['all']['flat'],
                  'flat_fine': g[v]['flat_fine_rel'],
                  'tex_mid': sum(mid) / len(mid)}
    texfine = sum(st['nocs'][t]['fine'] for t in tex) / len(tex)
    ratio = {t: st['nocs'][t]['fine'] / texfine
             for t in r['tiles'] if t.startswith('flat')}
    ok = [x['thrs'] for x in out.values()
          if x['flat'] <= TOL and x['flat_fine'] <= TOL]
    return out, ratio, (min(ok) if ok else None)


def summarize(results, session):
    L = []
    rows = []
    for r in results + session:
        d, ratio, low = derived(r)
        r['_d'], r['_ratio'], r['_low'] = d, ratio, low
    for r in results:
        d, dm = r['_d'], r['info']['demosaic']
        L.append(f"{r['name']}  ISO {r['iso']}  demosaic method "
                 f"{dm['demosaicing_method']} (LMMSE=6)  cs_radius "
                 f"{dm['cs_radius']:.3f}  user cs_thrs {r['user_thrs']:.2f}"
                 f"  cs_enabled {dm['cs_enabled']}  tiles "
                 f"{','.join(r['tiles'])} from {r['tiles_from']}")
        L.append('   thrs     mask_mean above_half edge_gain flat_gain '
                 'flat_fine tex_mid')
        for v, x in d.items():
            lab = tname(x['thrs']) + \
                ('*' if abs(x['thrs'] - r['user_thrs']) < 1e-6 else '')
            L.append(f"   {lab:<8} {x['mean']:9.4f} {x['above_half']:10.4f}"
                     f" {x['edge']:9.3f} {x['flat']:9.3f} "
                     f"{x['flat_fine']:9.3f} {x['tex_mid']:7.3f}")
        L.append('   (* = the user\'s threshold; all gains relative to '
                 'nocs; flat_fine and tex_mid are flat-tile fine / '
                 'tex-tile mid luma energy relative to nocs)')
        L.append('   nocs flat-tile fine energy / mean tex-tile fine '
                 'energy: ' + ', '.join(f'{t} {v:.2f}'
                                        for t, v in r['_ratio'].items()))
        L.append(f"   lowest threshold with flat_gain <= {TOL} and "
                 f"flat_fine <= {TOL}: "
                 + (f"{r['_low']:.2f}" if r['_low'] is not None else
                    'none up to 0.60'))
        L.append('')
    L.append('Combined, sorted by ISO (* = from the session 19 workflow '
             'sweep, which also tried 0.70)')
    L.append('ISO     image          mask_mean@0.33 flat_gain@0.33 '
             'edge_gain@0.33 lowest_passing  flat?  nocs flat/tex fine')
    for r in sorted(results + session, key=lambda r: r['iso']):
        x = r['_d']['thrs_0.33']
        flag = max(r['_ratio'].values()) >= FLAG
        low = f"{r['_low']:.2f}" if r['_low'] is not None else \
            ('none <= 0.70' if r in session else 'none <= 0.60')
        lab = r['name'] + ('*' if r in session else '')
        L.append(f"{r['iso']:<7} {lab:<14} {x['mean']:14.4f} "
                 f"{x['flat']:14.3f} {x['edge']:14.3f} {low:>14}  "
                 f"{'FLAG' if flag else '-':<5}  "
                 + ' '.join(f'{v:.2f}' for v in r['_ratio'].values()))
    L.append(f'FLAG: the nocs flat tile has fine-band energy >= {FLAG} of '
             'the mean tex tile (it may be texture, or at high ISO noise '
             'dominates both); judge on the montages.')
    return '\n'.join(L)


def main():
    xmp, hol, work, resdir, sess = sys.argv[1:6]
    specs = sys.argv[6:]
    for k in [k for k in os.environ
              if k.startswith('DT_DN_') or k.startswith('DT_CS_')]:
        del os.environ[k]
    os.makedirs(work, exist_ok=True)
    os.makedirs(resdir, exist_ok=True)
    sd, names = stage(xmp, hol, work, specs)
    results = []
    for n in names:
        res = rpu_cswf.process(sd, hol, work, n)
        montage(res, os.path.join(work, n),
                os.path.join(resdir, f'montage_{n}.jpg'))
        results.append(res)
        print(n, 'done', flush=True)
    session = list(json.load(open(sess)).values())
    json.dump({r['name']: r for r in results},
              open(os.path.join(resdir, 'metrics.json'), 'w'), indent=1)
    s = summarize(results, session)
    open(os.path.join(resdir, 'summary.txt'), 'w').write(s)
    print(s)


if __name__ == '__main__':
    main()
