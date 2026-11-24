# noise left on the flat wall against detail kept on the bird, per render
#
#   python3 tradeoff.py <render.png> [...]
#
# on 16-bit renders of P1378616 (--conf plugins/imageio/format/png/bpp=16),
# luminance, each crop normalized by its mean:
#   wall noise   RMS of (pixel - gaussian blur, sigma 6 px) on the wall crop:
#                grain, mottle up to about 6 px and specks all count
#   bird detail  the same on the bird crop, which is mostly feather texture
#   wall chroma  RMS spread of Lab a and b on the wall crop, x100
#   wall mottle  luminance band 2-16 px on the wall (blur 2 minus blur 16),
#                the blotches wall noise is too fine to see
# with equal wall noise, more bird detail means less structure was removed.
# A robust (MAD) measure was tried first and collapses to 0 on smoothed
# output while ignoring specks and mottle.
import subprocess
import sys

WALL = '360x260+1900+500'
BIRD = '360x260+2050+2050'


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


print(f'{"render":24s} wall noise  bird detail  ratio  wall chroma'
      '  wall mottle')
for p in sys.argv[1:]:
    w, b = hp_rms(p, WALL), hp_rms(p, BIRD)
    c = chroma_rms(p, WALL)
    m = hp_rms(p, WALL, '0x2', '0x16')
    name = p.rsplit('/', 1)[-1].removesuffix('.png')
    print(f'{name:24s} {w:10.4f}  {b:11.4f}  {b / w:5.2f}  {c:11.3f}'
          f'  {m:11.4f}')
