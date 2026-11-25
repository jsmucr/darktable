# noise left on the flat wall against detail kept on the bird, per render
#
#   python3 tradeoff.py <render.png | crop set> [...]
#
# a crop set is quick.sh output: <prefix> stands for <prefix>_wall.png,
# <prefix>_bird.png and <prefix>_grass.png, each region at MARGIN, MARGIN
#
# on 16-bit renders of P1378616 (--conf plugins/imageio/format/png/bpp=16),
# luminance, each crop normalized by its mean:
#   wall noise   RMS of (pixel - gaussian blur, sigma 6 px) on the wall crop:
#                grain, mottle up to about 6 px and specks all count
#   bird detail  the same on the bird crop, which is mostly feather texture
#   wall chroma  RMS spread of Lab a and b on the wall crop, x100
#   wall mottle  luminance band 2-16 px on the wall (blur 2 minus blur 16),
#                the blotches wall noise is too fine to see
#   specks       wall pixels more than 10% of the mean off their 5x5 median
#   grass specks the same on the grass crop, where texture lowers the
#                local thresholds; counts texture too (the JPEG has 1954)
#   rock chroma  (--rock) Lab a, b band 1-16 px RMS on the rock crop, x100,
#                and the correlation of a and b with L in that band: color
#                that follows the luma texture (session 10)
# with equal wall noise, more bird detail means less structure was removed.
# A robust (MAD) measure was tried first and collapses to 0 on smoothed
# output while ignoring specks and mottle.
import subprocess
import sys

WALL = '360x260+1900+500'
BIRD = '360x260+2050+2050'
GRASS = '360x260+600+3300'
ROCK = '360x260+2950+2530'
MARGIN = 300  # crop_xmp.py


def region(p, geo, tag):
    # full-frame render, or the matching file of a crop set
    if p.endswith('.png') or p.endswith('.JPG'):
        return p, geo
    return f'{p}_{tag}.png', geo.split('+')[0] + f'+{MARGIN}+{MARGIN}'


def hp_rms(path, geo, fine='0', coarse='0x6'):
    fmt = '%[fx:standard_deviation] %[fx:mean]'
    pre = ['-blur', fine] if fine != '0' else []
    out = subprocess.run(
        ['convert', path, '-crop', geo, '+repage', '-colorspace', 'gray',
         *pre, '(', '+clone', '-blur', coarse, ')',
         '-compose', 'mathematics', '-define', 'compose:args=0,1,-1,0.5',
         '-composite', '-format', fmt, 'info:'],
        capture_output=True, check=True, text=True).stdout.split()
    m = subprocess.run(['convert', path, '-crop', geo, '+repage', '-colorspace',
                        'gray', '-format', '%[fx:mean]', 'info:'],
                       capture_output=True, check=True, text=True).stdout
    return float(out[0]) / float(m)


def chroma_rms(path, geo):
    # Lab a and b spread over the flat wall, no high-pass: chroma noise
    # survives mostly as mottle coarser than the luma high-pass sees
    out = subprocess.run(
        ['convert', path, '-crop', geo, '+repage', '-colorspace', 'Lab',
         '-separate', '-format', '%[fx:standard_deviation]\n', 'info:'],
        capture_output=True, check=True, text=True).stdout.split()
    return 100 * (float(out[1]) ** 2 + float(out[2]) ** 2) ** 0.5


def specks(path, geo):
    # pixels more than 10% of the crop mean away from their 5x5 median
    m = subprocess.run(['convert', path, '-crop', geo, '+repage', '-colorspace',
                        'gray', '-format', '%[fx:mean]', 'info:'],
                       capture_output=True, check=True, text=True).stdout
    out = subprocess.run(
        ['convert', path, '-crop', geo, '+repage', '-colorspace', 'gray',
         '(', '+clone', '-statistic', 'median', '5x5', ')',
         '-compose', 'difference', '-composite', '-evaluate', 'divide', m,
         '-threshold', '10%', '-format', '%[fx:round(mean*w*h)]', 'info:'],
        capture_output=True, check=True, text=True).stdout
    return int(out)


def rock_chroma(path, geo):
    # band 1-16 px of L, a and b; spread of a, b and their correlation with L
    def band(ch):
        return ['(', path, '-crop', geo, '+repage', '-colorspace', 'Lab',
                '-channel', ch, '-separate', '+channel', '-blur', '0x1',
                '(', '+clone', '-blur', '0x16', ')', '-compose', 'mathematics',
                '-define', 'compose:args=0,1,-1,0.5', '-composite', ')']
    def run(args, fmt):
        return subprocess.run(['convert', *args, '-format', fmt, 'info:'],
                              capture_output=True, check=True,
                              text=True).stdout
    sd = {c: float(run(band(c), '%[fx:standard_deviation]')) for c in 'RGB'}
    def corr(c):
        m = float(run(band('R') + band(c) + ['-fx', '(u-0.5)*(v-0.5)+0.5'],
                      '%[fx:mean]')) - 0.5
        return m / (sd['R'] * sd[c]) if sd['R'] * sd[c] else 0.0
    return (100 * (sd['G'] ** 2 + sd['B'] ** 2) ** 0.5, corr('G'), corr('B'))


def main():
    rock = '--rock' in sys.argv
    if rock:
        sys.argv.remove('--rock')
    print(f'{"render":24s} wall noise  bird detail  ratio  wall chroma'
          '  wall mottle  specks  grass specks'
          + ('  rock chroma  corr(L,a)  corr(L,b)' if rock else ''))
    for p in sys.argv[1:]:
        wall, bird, grass = (region(p, WALL, 'wall'), region(p, BIRD, 'bird'),
                             region(p, GRASS, 'grass'))
        w, b = hp_rms(*wall), hp_rms(*bird)
        c = chroma_rms(*wall)
        m = hp_rms(*wall, '0x2', '0x16')
        name = p.rsplit('/', 1)[-1].removesuffix('.png')
        print(f'{name:24s} {w:10.4f}  {b:11.4f}  {b / w if w else float('inf'):5.2f}  {c:11.3f}'
              f'  {m:11.4f}  {specks(*wall):6d}  {specks(*grass):12d}', end='')
        if rock:
            rc = rock_chroma(*region(p, ROCK, 'rock'))
            print(f'  {rc[0]:11.3f}  {rc[1]:9.2f}  {rc[2]:9.2f}', end='')
        print()


if __name__ == '__main__':
    main()
