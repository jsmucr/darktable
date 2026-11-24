#!/bin/bash
# re-run the session 5 measurements on the ISO 20000 sample
#
#   ./perchannel.sh [raw] [workdir]
#
# applies perchannel.patch and instrumentation.patch to
# src/iop/denoiseprofile.c, rebuilds that module in ../build (BUILD=... to
# override), dumps the module's detail bands on three flat patches with the
# per-channel switch off and on, measures them, and reverts both patches on
# exit. Then repeats the RCD export with and without white balance.
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
raw=${1:-/c/temp/denoise/P1378616.RW2}
work=${2:-/tmp/dn-perchannel}
build=${BUILD:-$src/build}
pics=$HOME/Pictures/Darktable/20260430_no_name
template=${TEMPLATE:-$pics/20260430_0012.RW2.xmp}
mkdir -p "$work"

patches="$here/perchannel.patch $here/instrumentation.patch"
restore() {
  git -C "$src" checkout -- src/iop/denoiseprofile.c
  cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null
}
git -C "$src" diff --quiet -- src/iop/denoiseprofile.c || {
  echo "src/iop/denoiseprofile.c has local changes, not touching it" >&2
  exit 1
}
for p in $patches; do git -C "$src" apply "$p"; done
trap restore EXIT
cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null

python3 "$here/variants_xmp.py" "$template" 2.176e-4 "$work"
cli() {
  "$build/bin/darktable-cli" "$raw" "$1" "$2" --apply-custom-presets false \
    --core --configdir "$work/cfg" --library :memory: "${@:3}" >/dev/null 2>&1
}
dirs=""
for patch in "800 150 480 320:wall" "3100 850 480 200:mid" \
             "3100 1290 480 150:bright"; do
  crop=${patch%%:*}
  tag=${patch##*:}
  for v in wav_default_rgb wav_default; do
    for sw in off on; do
      d="$work/${v}_${tag}_$sw"
      mkdir -p "$d"
      if [ $sw = on ]; then
        DT_DN_PERCHANNEL=1 DT_DN_DUMP="$d" DT_DN_CROP="$crop" \
          cli "$work/$v.xmp" "$work/out.png"
      else
        DT_DN_DUMP="$d" DT_DN_CROP="$crop" cli "$work/$v.xmp" "$work/out.png"
      fi
      dirs="$dirs $d"
    done
  done
done
cd "$here"
python3 detail_noise.py $dirs | grep -E '^wav|s0|s1:'

# white balance before demosaic changes the per-channel noise
python3 profiling_xmp.py "$src" "$work"
python3 - "$work" <<'EOF'
import struct, sys
w = sys.argv[1]
x = open(f'{w}/prof_rcd.xmp').read()
old = '0000803f0000803f0000803f0000c07f'
new = struct.pack('<4f', 2.4140625, 1.0, 1.828125, float('nan')).hex()
assert x.count(old) == 1
open(f'{w}/prof_rcd_wb.xmp', 'w').write(x.replace(old, new))
EOF
for t in rcd rcd_wb; do
  cli "$work/prof_$t.xmp" "$work/$t.pfm" \
    --conf plugins/lighttable/export/iccprofile=image \
    --conf plugins/lighttable/export/style=none
done
python3 - "$work" <<'EOF'
import math, statistics as st, sys
from pfm import crop, plane
from bands import band_sigmas
w = sys.argv[1]
aG, bG = 2.176e-4, 1.27e-6
for t, wb in (('rcd', (1, 1, 1)), ('rcd_wb', (2.4140625, 1.0, 1.828125))):
    img = crop(f'{w}/{t}.pfm', 800, 150, 480, 320)
    out = []
    for c in range(3):
        p = [[v / wb[c] for v in r] for r in plane(img, c)]
        m = st.fmean(v for r in p for v in r)
        s0 = band_sigmas(p, 1)[0] / math.sqrt(aG * m + bG)
        out.append(f"{'RGB'[c]} s0={s0:.2f}")
    print(f'export {t:7s} ' + '  '.join(out))
EOF
rm -rf "$work"/*.pfm "$work/cfg" "$here/__pycache__"
