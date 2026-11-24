#!/bin/bash
# re-run the session 6 and 7 measurements on the ISO 20000 sample
#
#   ./bandnoise.sh [raw] [workdir]
#
# applies bandnoise.patch to src/iop/denoiseprofile.c (self-contained: it
# carries its own detail-band dump, do not stack instrumentation.patch on
# it), rebuilds that module in ../build (BUILD=... to override), checks that
# the output is unchanged with the switches off, renders the strength sweeps
# and the variants of the measured-noise mode, prints tradeoff.py for all of
# them and the per-scale noise on the flat wall, and reverts the patch on
# exit. Takes about 20 minutes and leaves about 3.3 GB of renders.
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
raw=${1:-/c/temp/denoise/P1378616.RW2}
work=${2:-/tmp/dn-bandnoise}
build=${BUILD:-$src/build}
pics=$HOME/Pictures/Darktable/20260430_no_name
template=${TEMPLATE:-$pics/20260430_0012.RW2.xmp}
mkdir -p "$work/off" "$work/ref"

restore() {
  git -C "$src" checkout -- src/iop/denoiseprofile.c
  cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null
}
git -C "$src" diff --quiet -- src/iop/denoiseprofile.c || {
  echo "src/iop/denoiseprofile.c has local changes, not touching it" >&2
  exit 1
}
python3 "$here/variants_xmp.py" "$template" 2.176e-4 "$work"
cli() {
  rm -f "$2"
  "$build/bin/darktable-cli" "$raw" "$1" "$2" --apply-custom-presets false \
    --core --configdir "$work/cfg" --library :memory: "${@:3}" >/dev/null 2>&1
}
png16() { cli "$1" "$2" --conf plugins/imageio/format/png/bpp=16; }

# reference renders from the clean module
cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null
same="wav_default wav_default_rgb wav_strong nlm_auto"
for v in $same; do cli "$work/$v.xmp" "$work/ref/$v.pfm"; done

git -C "$src" apply "$here/bandnoise.patch"
trap restore EXIT
cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null
for v in $same; do
  cli "$work/$v.xmp" "$work/off/$v.pfm"
  cmp -s "$work/ref/$v.pfm" "$work/off/$v.pfm" && echo "switch off: $v identical" \
    || echo "switch off: $v DIFFERS"
done

for s in 1.0 1.5 2.0 3.0 4.0; do png16 "$work/sw_old_s$s.xmp" "$work/sw_old_s$s.png"; done
for s in 0.75 1.0 1.25 1.5 2.0; do
  DT_DN_BANDNOISE=1 png16 "$work/sw_bn_s$s.xmp" "$work/sw_bn_s$s.png"
  DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 \
    png16 "$work/sw_bn_s$s.xmp" "$work/once_s$s.png"
done
for s in 1.0 1.25; do
  for k in 1.0 1.5 2.0; do
    DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BNKMIN=$k \
      png16 "$work/sw_bn_s$s.xmp" "$work/floor_s${s}_k$k.png"
  done
done
for k in 1.0 1.5 2.0 2.5 3.0; do
  DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BNK=$k \
    png16 "$work/sw_bn_s1.0.xmp" "$work/fixed_k$k.png"
done
# model-shaped thresholds: floored at the model, and the model alone
for s in 1.0 1.25; do
  DT_DN_BANDNOISE=1 DT_DN_BNFLOOR=1 png16 "$work/sw_bn_s$s.xmp" "$work/mfloor_s$s.png"
  DT_DN_BANDNOISE=1 DT_DN_BNGAIN=1 png16 "$work/sw_bn_s$s.xmp" "$work/model_s$s.png"
done
python3 "$here/tradeoff.py" "$work"/sw_old_*.png "$work"/sw_bn_*.png \
  "$work"/once_*.png "$work"/floor_*.png "$work"/fixed_*.png \
  "$work"/mfloor_*.png "$work"/model_*.png "${raw%.*}.JPG"

# session 7: local BayesShrink, without and with leave-one-out
for r in 2 4; do
  for s in 1.0 1.1 1.15 1.25; do
    DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BNLOCAL=$r DT_DN_BNLOO=1 \
      png16 "$work/sw_bn_s$s.xmp" "$work/loo_r${r}_s$s.png"
  done
done
for s in 1.0 1.25; do
  DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BNLOCAL=4 \
    png16 "$work/sw_bn_s$s.xmp" "$work/local_r4_s$s.png"
done
python3 "$here/tradeoff.py" "$work"/sw_old_s3.0.png \
  "$work"/floor_s1.25_k1.0.png "$work"/local_*.png "$work"/loo_*.png \
  "${raw%.*}.JPG"

# per-scale estimates (whole frame) and the noise actually on the wall
mkdir -p "$work/dump"
DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BANDNOISE_LOG=1 DT_DN_THRLOG=1 \
  DT_DN_DUMP="$work/dump" DT_DN_CROP="800 150 480 320" \
  "$build/bin/darktable-cli" "$raw" "$work/sw_bn_s1.25.xmp" "$work/out.png" \
  --apply-custom-presets false --core --configdir "$work/cfg" \
  --library :memory: 2>&1 | grep -E '^\[(bandnoise|thr)\]'
cd "$here"
python3 detail_noise.py "$work/dump"
rm -rf "$work"/*.pfm "$work"/off "$work"/ref "$work/cfg" "$here/__pycache__"
