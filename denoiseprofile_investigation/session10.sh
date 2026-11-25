#!/bin/bash
# re-run the session 10 measurements on the ISO 20000 sample
#
#   ./session10.sh [workdir]
#
# builds the session 9 base history without and with demosaic capture
# sharpening (base_xmp.py), applies bandnoise.patch to
# src/iop/denoiseprofile.c, rebuilds that module in ../build (BUILD=... to
# override), renders old mode on full frames and the measured-noise
# variants as crop sets (quick.sh), checks one crop set against its full
# frame, prints tradeoff.py --rock, and reverts the patch on exit. Takes
# about 9 minutes; the off-switch check is in bandnoise.sh.
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
work=${1:-/tmp/dn-session10}
build=${BUILD:-$src/build}
raw=${RAW:-/c/temp/denoise/P1378616.RW2}
pics=$HOME/Pictures/Darktable/20260430_no_name
template=${TEMPLATE:-$pics/20260430_0012.RW2.xmp}
mkdir -p "$work/off/xmp" "$work/cs/xmp"

restore() {
  git -C "$src" checkout -- src/iop/denoiseprofile.c
  cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null
}
git -C "$src" diff --quiet -- src/iop/denoiseprofile.c || {
  echo "src/iop/denoiseprofile.c has local changes, not touching it" >&2
  exit 1
}
git -C "$src" apply "$here/bandnoise.patch"
trap restore EXIT
cmake --build "$build" --target denoiseprofile -j"$(nproc)" >/dev/null

# capture sharpening at the values darktable autotunes for this file
python3 "$here/base_xmp.py" "$template" "$work/base_off.xmp" 2.9
python3 "$here/base_xmp.py" "$template" "$work/base_cs.xmp" 2.9 0.53,0.45
for b in off cs; do
  python3 "$here/variants_xmp.py" "$work/base_$b.xmp" 2.176e-4 "$work/$b/xmp"
done

full() {
  local c
  c=$(mktemp -d)
  env "${@:3}" "$build/bin/darktable-cli" "$raw" "$1" "$2" \
    --apply-custom-presets false --core --configdir "$c" --library :memory: \
    --conf plugins/imageio/format/png/bpp=16 >/dev/null 2>&1
  rm -rf "$c"
}
new="DT_DN_BNLOCAL=8 DT_DN_BNWIENER=y DT_DN_BNLBO=1 DT_DN_DESPECK=2"
for b in off cs; do
  for v in old_s2.0 old_s3.0 oldw_s3.0; do
    full "$work/$b/xmp/sw_$v.xmp" "$work/$b/full_$v.png" &
  done
done
wait

q="$here/quick.sh"
for b in off cs; do
  export WORK=$work/$b TEMPLATE=$work/base_$b.xmp
  for s in 1.0 1.1 1.2; do
    "$q" new_s$s bn $s $new
    "$q" neww_s$s bnw $s $new
  done
  for s in 1.1 1.2; do
    "$q" guide_s$s bn $s $new DT_DN_BNCGUIDE=1
    "$q" guidew_s$s bnw $s $new DT_DN_BNCGUIDE=1
  done
done

full "$work/cs/xmp/sw_bnw_s1.2.xmp" "$work/cs/full_guidew_s1.2.png" \
  DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 $new DT_DN_BNCGUIDE=1
python3 "$here/tradeoff.py" --rock "$work/cs/full_guidew_s1.2.png" \
  "$work/cs/guidew_s1.2" | tail -2

for b in off cs; do
  echo "== base $b"
  sets=""
  for v in new_s1.0 new_s1.1 new_s1.2 neww_s1.0 neww_s1.1 neww_s1.2 \
           guide_s1.1 guide_s1.2 guidew_s1.1 guidew_s1.2; do
    sets="$sets $work/$b/$v"
  done
  python3 "$here/tradeoff.py" --rock "$work/$b"/full_*.png $sets \
    "${raw%.*}.JPG"
done
rm -rf "$here/__pycache__"
