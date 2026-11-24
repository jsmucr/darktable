# write variants of tools/noise/profiling-shot.xmp with an explicit demosaic
# entry, so the noise measurement does not depend on the current default
#
#   python3 profiling_xmp.py <darktable-src> <outdir>
#
# writes prof_ppg.xmp, prof_rcd.xmp and cfa.xmp (passthrough monochrome: one
# raw photosite value per pixel, copied to all three channels)
import os
import re
import struct
import sys

src, outdir = sys.argv[1], sys.argv[2]
xmp = open(os.path.join(src, 'tools/noise/profiling-shot.xmp')).read()

# dt_iop_demosaic_params_t, version 8 (src/iop/demosaic.c)
methods = {'ppg': 0, 'rcd': 5, 'cfa': 3}
blend = 'gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU='

n = len(re.findall(r'darktable:operation=', xmp))
for name, method in methods.items():
    p = struct.pack('<ifiiiffffififfi', 0, 0.0, 0, method, 1, 0.2, 0.5, 0.4,
                    0.0, 8, 0.0, 0, 0.0, 0.0, 1).hex()
    li = (f'     <rdf:li darktable:num="{n}" darktable:operation="demosaic"'
          f' darktable:enabled="1" darktable:modversion="8"\n'
          f'      darktable:params="{p}" darktable:multi_name=""'
          f' darktable:multi_priority="0"\n'
          f'      darktable:blendop_version="14"'
          f' darktable:blendop_params="{blend}"/>\n    </rdf:Seq>')
    h = xmp.find('</darktable:history>')
    i = xmp.rfind('</rdf:Seq>', 0, h)
    y = xmp[:i].rstrip() + '\n' + li + xmp[i + len('</rdf:Seq>'):]
    y = re.sub(r'darktable:history_end="\d+"',
               f'darktable:history_end="{n + 1}"', y)
    out = 'cfa.xmp' if name == 'cfa' else f'prof_{name}.xmp'
    open(os.path.join(outdir, out), 'w').write(y)
