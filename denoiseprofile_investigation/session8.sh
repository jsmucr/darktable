#!/bin/bash
# re-run the session 8 measurements on the ISO 20000 sample
#
#   ./session8.sh [workdir]
#
# applies bandnoise.patch to src/iop/denoiseprofile.c, rebuilds that module
# in ../build (BUILD=... to override), renders the session's variants as
# crop sets with quick.sh, checks three of them against full-frame renders,
# prints tradeoff.py for all of them, and reverts the patch on exit. Takes
# about 6 minutes; the off-switch check is in bandnoise.sh.
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
export WORK=${1:-/tmp/dn-session8}
build=${BUILD:-$src/build}
raw=${RAW:-/c/temp/denoise/P1378616.RW2}
mkdir -p "$WORK"

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

q="$here/quick.sh"
w="DT_DN_BNWIENER=y DT_DN_BNLBO=1"
sets=""
r() { "$q" "$@"; sets="$sets $WORK/$1"; }
# session 7 reference and the despeck pre-pass alone
for s in 1.1 1.25; do r loo_r4_s$s bn $s DT_DN_BNLOCAL=4 DT_DN_BNLOO=1; done
for k in 2 3; do r loo_r4_ds${k}_s1.1 bn 1.1 DT_DN_BNLOCAL=4 DT_DN_BNLOO=1 \
  DT_DN_DESPECK=$k; done
# leave-block-out, Wiener on all channels and on luma only
r lbo1_r4_s1.1 bn 1.1 DT_DN_BNLOCAL=4 DT_DN_BNLBO=1
r wiener_r4_s1.25 bn 1.25 DT_DN_BNLOCAL=4 DT_DN_BNWIENER=1 DT_DN_BNLBO=1
for s in 1.1 1.2 1.25; do r r4_s$s bn $s DT_DN_BNLOCAL=4 $w; done
# window radius and despeck level
for rad in 6 8 16; do
  for s in 1.0 1.1; do
    r r${rad}_s$s bn $s DT_DN_BNLOCAL=$rad $w
    for k in 2 3; do
      r r${rad}_ds${k}_s$s bn $s DT_DN_BNLOCAL=$rad $w DT_DN_DESPECK=$k
    done
  done
done

# crop sets against full frames
for v in "r8_ds2_s1.1 1.1 8 2" "r16_ds2_s1.1 1.1 16 2" "r4_s1.2 1.2 4 0"; do
  set -- $v
  c=$(mktemp -d)
  env DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BNLOCAL=$3 $w \
    $([ "$4" != 0 ] && echo DT_DN_DESPECK=$4) \
    "$build/bin/darktable-cli" "$raw" "$WORK/xmp/sw_bn_s$2.xmp" \
    "$WORK/full_$1.png" --apply-custom-presets false --core --configdir "$c" \
    --library :memory: --conf plugins/imageio/format/png/bpp=16 >/dev/null 2>&1
  rm -rf "$c"
  python3 "$here/tradeoff.py" "$WORK/full_$1.png" "$WORK/$1" | tail -2
done

python3 "$here/tradeoff.py" $sets "${raw%.*}.JPG"
rm -rf "$here/__pycache__"
