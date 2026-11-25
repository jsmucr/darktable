# the base history for P1378616 comparisons from session 9 on: the
# template's exposure and sigmoid only, everything else at darktable's
# defaults (as-shot white balance, no color calibration), exposure raised
# to match the camera JPEG's brightness, optionally with the demosaic
# module's capture sharpening
#
#   python3 base_xmp.py <template.xmp> <out.xmp> [ev] [cs]
#
# ev: exposure in EV (default 2.9, session 9). cs: "off" (default), "auto"
# (capture sharpening on, radius 0 so that darktable autotunes it), or
# "radius,threshold" with fixed values. variants_xmp.py appends denoise
# entries to the result.
import re
import struct
import sys

template, out = sys.argv[1], sys.argv[2]
ev = float(sys.argv[3]) if len(sys.argv) > 3 else 2.9
cs = sys.argv[4] if len(sys.argv) > 4 else 'off'
BLEND = 'gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU='


def demosaic(radius, thrs):
    # dt_iop_demosaic_params_t, version 8 (src/iop/demosaic.c:144), at its
    # defaults (RCD) apart from capture sharpening, which is enabled
    b = struct.pack('<ifiiiffffififfi',
                    0, 0.0, 0, 5, 1, 0.2,       # green_eq .. dual_thrs
                    radius, thrs, 0.0, 8, 0.0,  # cs_radius .. cs_center
                    1, 0.0, 0.0, 1)             # cs_enabled .. dng_gainmap
    assert len(b) == 60
    return b.hex()


x = open(template).read()
items = re.findall(r'<rdf:li\s[^>]*?darktable:operation="(\w+)"[^>]*?/>', x,
                   re.S)
entries = re.findall(r'(<rdf:li\s[^>]*?darktable:operation="\w+"[^>]*?/>)',
                     x, re.S)
keep = [e for e, op in zip(entries, items) if op in ('exposure', 'sigmoid')]
assert len(keep) == 2

exp = keep[0] if 'operation="exposure"' in keep[0] else keep[1]
p = re.search(r'params="([0-9a-f]+)"', exp).group(1)
v = list(struct.unpack('<iffffii', bytes.fromhex(p)))
v[2] = ev
keep[keep.index(exp)] = exp.replace(p, struct.pack('<iffffii', *v).hex())

if cs != 'off':
    r, t = (0.0, 0.45) if cs == 'auto' else map(float, cs.split(','))
    keep.insert(0, '<rdf:li darktable:num="0" darktable:operation="demosaic"'
                ' darktable:enabled="1"\n'
                f'      darktable:modversion="8" darktable:params="{demosaic(r, t)}"'
                ' darktable:multi_name="" darktable:multi_priority="0"\n'
                '      darktable:blendop_version="14"'
                f' darktable:blendop_params="{BLEND}"/>')

body = ''.join('     ' + re.sub(r'darktable:num="\d+"', f'darktable:num="{k}"', e)
               + '\n' for k, e in enumerate(keep))
start = x.index('<rdf:Seq>', x.index('<darktable:history>')) + len('<rdf:Seq>\n')
end = x.index('    </rdf:Seq>\n   </darktable:history>')
y = x[:start] + body + x[end:]
y = re.sub(r'darktable:history_end="\d+"',
           f'darktable:history_end="{len(keep)}"', y)
y = y.replace('auto_presets_applied="1"', 'auto_presets_applied="0"')
y = re.sub(r'\s*darktable:iop_order_version="\d+"', '', y)
y = re.sub(r'\s*darktable:iop_order_list="[^"]*"', '', y)
open(out, 'w').write(y)
