# pick raw.pixls.us samples for the Y0 row test: cameras with a darktable
# noise profile, full-size raws only, the highest-ISO sample per camera
#
#   python3 rpu_pick.py <noiseprofiles.json> <repo.json> <out.json>
#
# repo.json is https://raw.pixls.us/json/getrepository.php?set=all. Reads
# each candidate's exif text (cached next to out.json) for ISO and
# Exif.Photo.ISOSpeedRatings / PhotographicSensitivity.
import concurrent.futures
import json
import os
import re
import sys
import urllib.parse
import urllib.request

SKIP = re.compile(r'sraw|mraw|small|medium|crop|chdk|dng|1:1|16:9', re.I)


def exif(url, cache):
    path = os.path.join(cache, re.sub(r'\W', '_', url)[-120:])
    if not os.path.exists(path):
        q = urllib.parse.quote(url, safe=':/')
        with urllib.request.urlopen(q, timeout=60) as r:
            open(path, 'wb').write(r.read())
    return open(path, errors='replace').read()


def main():
    profiles, repo, out = sys.argv[1:4]
    prof = {}
    for m in json.load(open(profiles))['noiseprofiles']:
        for mo in m['models']:
            prof[(m['maker'].lower(), mo['model'].lower())] = \
                [p['iso'] for p in mo['profiles']]
    cache = os.path.join(os.path.dirname(os.path.abspath(out)), 'exif')
    os.makedirs(cache, exist_ok=True)
    rows = []
    for make, model, mode, mp, _, lic, _, raw, ex in \
            json.load(open(repo))['data']:
        if (make.lower(), model.lower()) not in prof or SKIP.search(mode):
            continue
        rawurl = re.search(r"href='([^']+)'", raw)
        exurl = re.search(r"href='([^']+)'", ex)
        if not rawurl or not exurl:
            continue
        rawurl = rawurl.group(1)
        if rawurl.lower().endswith('.dng'):
            continue
        rows.append({'make': make, 'model': model, 'mode': mode,
                     'raw': rawurl, 'cc0': '>co<' in lic,
                     'size': re.search(r'\(([\d.]+)MB\)', raw).group(1),
                     'exif': exurl.group(1)})

    def one(r):
        t = exif(r['exif'], cache)
        m = re.search(r'^Exif\.Photo\.(?:ISOSpeedRatings|'
                      r'PhotographicSensitivity)\s+(\d+)', t, re.M)
        r['iso'] = int(m.group(1)) if m else 0
        return r

    with concurrent.futures.ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(one, rows))
    best = {}
    for r in rows:
        k = (r['make'], r['model'])
        if r['iso'] > best.get(k, {'iso': -1})['iso']:
            best[k] = r
    picked = sorted(best.values(), key=lambda r: -r['iso'])
    json.dump(picked, open(out, 'w'), indent=1)
    for r in picked[:60]:
        print(r['iso'], r['make'], r['model'], r['mode'], r['size'],
              'cc0' if r['cc0'] else '')


if __name__ == '__main__':
    main()
