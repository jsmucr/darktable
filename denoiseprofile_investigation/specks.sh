#!/bin/bash
# re-run the session 4 speck trace on the ISO 20000 sample
#
#   ./specks.sh [raw] [workdir]
#
# applies instrumentation.patch to src/iop/denoiseprofile.c, rebuilds that
# module in ../build-dn (BUILD=... to override), renders the strength-2
# wavelet variants with their internal buffers dumped for the wall crop,
# then reverts the patch and rebuilds the module clean
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
raw=${1:-/c/temp/denoise/P1378616.RW2}
work=${2:-/tmp/dn-specks}
build=${BUILD:-$src/build-dn}
pics=$HOME/Pictures/Darktable/20260430_no_name
template=${TEMPLATE:-$pics/20260430_0012.RW2.xmp}
crop="1900 500 360 260"
mkdir -p "$work"

restore() {
  git -C "$src" apply -R "$here/instrumentation.patch"
  cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null
}
git -C "$src" apply "$here/instrumentation.patch"
trap restore EXIT
cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null

python3 "$here/variants_xmp.py" "$template" 2.176e-4 "$work"
cd "$here"
for v in wav_strong wav_strong_sh0 wav_strong_sh05 wav_strong_sh18 \
         wav_strong_rgb; do
  mkdir -p "$work/$v"
  thr=$(DT_DN_DUMP="$work/$v" DT_DN_CROP="$crop" "$build/bin/darktable-cli" \
          "$raw" "$work/$v.xmp" "$work/$v.png" --apply-custom-presets false \
          --core --configdir "$work/cfg" --library :memory: 2>&1 \
        | sed -n 's/.*scale 0 .* thrs \([^ ]*\) .*/\1/p')
  echo "== $v (scale 0 threshold, channel 0: $thr)"
  python3 specks.py "$work/$v" "$thr" | grep -E '^[0-9]+ specks|^specks'
  python3 tails.py "$work/$v" | grep transformed
done
rm -rf "$work"/cfg "$here/__pycache__"
