# append denoise (profiled) / raw denoise entries to an existing darktable
# history, one output XMP per variant
#
#   python3 variants_xmp.py <template.xmp> <green a of the profile> <outdir>
#
# the template must end its history at num 10 (history_end="11"); the one
# used so far is the scene-referred default history of
# ~/Pictures/Darktable/20260430_no_name/20260430_0012.RW2.xmp, which carries
# that image's white balance and color calibration
import math
import os
import struct
import sys

template, a, outdir = sys.argv[1], float(sys.argv[2]), sys.argv[3]
BLEND = 'gz11eJxjYIAACQYYOOHEgAZY0QWAgBGLGANDgz0Ej1Q+dcF/IADRAGpyHQU='


def denoiseprofile(mode=1, strength=1.0, luma=0.5, chroma=0.5, gain=1.0,
                   color=1, shadows=None):
    # dt_iop_denoiseprofile_params_t, version 12: 416 bytes
    # mode: 0 nlmeans, 1 wavelets, 3 nlmeans auto, 4 wavelets auto
    # color: 0 RGB, 1 Y0U0V0; luma/chroma are flat curve heights (0.5 = off)
    # the infer_* values repeat src/iop/denoiseprofile.c:2637-2655, as
    # reload_defaults() would set them; shadows overrides the inferred value
    ag = a * gain
    radius = float(min(int(1 + ag * 15000 + ag * ag * 300000), 8))
    scattering = min(3000 * ag, 1.0)
    if shadows is None:
        shadows = min(max(0.1 - 0.1 * math.log(ag), 0.7), 1.8)
    bias = -max(5 + 0.5 * math.log(ag), 0.0)
    f = [radius, 7.0, strength, shadows, bias, scattering, 0.1, gain,
         -1.0, 0, 0, 0, 0, 0]  # a[0] = -1: autodetect the profile
    b = struct.pack('<14f', *f) + struct.pack('<i', mode)
    b += struct.pack('<42f', *([k / 6.0 for k in range(7)] * 6))
    ys = []
    for ch in range(6):  # all, R, G, B, Y0, U0V0
        ys += [luma if ch == 4 else chroma if ch == 5 else 0.5] * 7
    b += struct.pack('<42f', *ys) + struct.pack('<5i', 1, 1, 1, color, 0)
    assert len(b) == 416
    return b.hex()


def rawdenoise(threshold):
    # dt_iop_rawdenoise_params_t, version 2
    b = struct.pack('<f', threshold)
    b += struct.pack('<20f', *([k / 4.0 for k in range(5)] * 4))
    b += struct.pack('<20f', *([0.5] * 20))
    return b.hex()


VARIANTS = {
    'none': [],
    'wav_default': [('denoiseprofile', 12, denoiseprofile())],
    'wav_default_rgb': [('denoiseprofile', 12, denoiseprofile(color=0))],
    'wav_strong': [('denoiseprofile', 12,
                    denoiseprofile(strength=2.0, chroma=0.8, luma=0.6))],
    'wav_strong_rgb': [('denoiseprofile', 12,
                        denoiseprofile(strength=2.0, chroma=0.8, luma=0.6,
                                       color=0))],
    'wav_strong_sh0': [('denoiseprofile', 12,
                        denoiseprofile(strength=2.0, chroma=0.8, luma=0.6,
                                       shadows=0.0))],
    'wav_strong_sh05': [('denoiseprofile', 12,
                         denoiseprofile(strength=2.0, chroma=0.8, luma=0.6,
                                        shadows=0.5))],
    'wav_strong_sh18': [('denoiseprofile', 12,
                         denoiseprofile(strength=2.0, chroma=0.8, luma=0.6,
                                        shadows=1.8))],
    'wav_fine': [('denoiseprofile', 12,
                  denoiseprofile(strength=1.5, luma=0.7, chroma=0.8))],
    'nlm_auto': [('denoiseprofile', 12, denoiseprofile(mode=3))],
    'nlm_auto_x3': [('denoiseprofile', 12, denoiseprofile(mode=3, gain=3.0))],
    'raw05': [('rawdenoise', 2, rawdenoise(0.05))],
    'raw02_wav': [('rawdenoise', 2, rawdenoise(0.02)),
                  ('denoiseprofile', 12, denoiseprofile())],
    'raw05_wav': [('rawdenoise', 2, rawdenoise(0.05)),
                  ('denoiseprofile', 12, denoiseprofile())],
    'raw02_nlm': [('rawdenoise', 2, rawdenoise(0.02)),
                  ('denoiseprofile', 12, denoiseprofile(mode=3))],
    # round 2: settings tried with the measured-noise experiment
    'bn_c1': [('denoiseprofile', 12, denoiseprofile(chroma=1.0))],
    'bn_c1_sh05': [('denoiseprofile', 12,
                    denoiseprofile(chroma=1.0, shadows=0.5))],
    'bn_s15_c1_sh05': [('denoiseprofile', 12,
                        denoiseprofile(strength=1.5, chroma=1.0,
                                       shadows=0.5))],
    'bn_s15_l06_c1_sh05': [('denoiseprofile', 12,
                            denoiseprofile(strength=1.5, luma=0.6,
                                           chroma=1.0, shadows=0.5))],
}
# round 2 strength sweeps: old mode, and measured-noise mode at chroma 1
for s in (1.0, 1.5, 2.0, 3.0, 4.0):
    VARIANTS[f'sw_old_s{s}'] = [('denoiseprofile', 12, denoiseprofile(
        strength=s, chroma=0.8, shadows=0.5))]
for s in (0.75, 1.0, 1.1, 1.15, 1.2, 1.25, 1.3, 1.5, 2.0):
    VARIANTS[f'sw_bn_s{s}'] = [('denoiseprofile', 12, denoiseprofile(
        strength=s, chroma=1.0, shadows=0.5))]

x = open(template).read()
end = '    </rdf:Seq>\n   </darktable:history>'
assert end in x and 'history_end="11"' in x
for name, items in VARIANTS.items():
    s = ''
    for k, (op, ver, p) in enumerate(items):
        s += (f'     <rdf:li darktable:num="{11 + k}"'
              f' darktable:operation="{op}" darktable:enabled="1"\n'
              f'      darktable:modversion="{ver}" darktable:params="{p}"'
              f' darktable:multi_name="" darktable:multi_priority="0"\n'
              f'      darktable:blendop_version="14"'
              f' darktable:blendop_params="{BLEND}"/>\n')
    y = x.replace(end, s + end, 1).replace(
        'history_end="11"', f'history_end="{11 + len(items)}"')
    open(os.path.join(outdir, f'{name}.xmp'), 'w').write(y)
