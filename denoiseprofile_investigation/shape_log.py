# log the measured band noise per scale, relative to the finest band, for
# images holiday.py has processed
#
#   python3 shape_log.py <workdir> <out.json> [cs|nocs] [name ...]
#
# renders each image's sw_bnw_s1.0 history at full size (capture
# sharpening on, as in holiday.py; nocs: the same without the demosaic
# entry, so capture sharpening off) with DT_DN_BANDNOISE_LOG and the
# session 10 switches, and stores the logged estimates. Needs
# bandnoise.patch applied and built.
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import holiday  # noqa: E402

SRC_DIR = '/c/temp/denoise/holiday'


def estimates(work, name, cs):
    d = os.path.join(work, name)
    xmp = os.path.join(d, 'xmp', 'sw_bnw_s1.0.xmp')
    if cs == 'nocs':
        # the same history without the demosaic entry: darktable's default
        # demosaic, capture sharpening off
        x = open(xmp).read()
        x2 = re.sub(r'\s*<rdf:li\s[^>]*?darktable:operation="demosaic"[^>]*?/>',
                    '', x, count=1, flags=re.S)
        assert x2 != x
        n = int(re.search(r'history_end="(\d+)"', x2).group(1))
        x2 = x2.replace(f'history_end="{n}"', f'history_end="{n - 1}"')
        nums = iter(range(100))
        x2 = re.sub(r'darktable:num="\d+"', lambda m: f'darktable:num="{next(nums)}"', x2)
        fd, xmp = tempfile.mkstemp(suffix='.xmp')
        os.write(fd, x2.encode())
        os.close(fd)
    env = dict(holiday.NEW, DT_DN_BANDNOISE_LOG='1')
    with tempfile.TemporaryDirectory() as tmp:
        out = holiday.run([holiday.CLI, os.path.join(SRC_DIR, name + '.RW2'),
                           xmp, os.path.join(tmp, 'x.png'),
                           '--apply-custom-presets', 'false', '--core',
                           '--configdir', tmp, '--library', ':memory:'],
                          env).stderr
    if cs == 'nocs':
        os.remove(xmp)
    s0 = [float(v) for v in re.search(r'scale-0 noise (\S+) (\S+) (\S+),',
                                      out).groups()]
    per = [[float(v) for v in m.groups()] for m in re.finditer(
        r'scale \d+ noise x strength (\S+) (\S+) (\S+)', out)]
    iso = json.load(open(os.path.join(d, 'metrics.json')))['iso']
    return name, {'iso': iso, 's0': s0, 'scales': per[:7]}


def main():
    work, out, cs = sys.argv[1], sys.argv[2], sys.argv[3]
    names = sys.argv[4:]
    res = json.load(open(out)) if os.path.exists(out) else {}
    todo = [n for n in names if n not in res]
    with concurrent.futures.ThreadPoolExecutor(3) as ex:
        for name, r in ex.map(lambda n: estimates(work, n, cs), todo):
            res[name] = r
            json.dump(res, open(out, 'w'), indent=1)
            print(name, r['iso'], flush=True)


if __name__ == '__main__':
    main()
