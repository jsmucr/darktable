#!/bin/bash
# fast iteration: render only the tradeoff.py regions of P1378616
#
#   ./quick.sh <name> <old|bn|bnw> <strength> [VAR=value ...]
#
# bnw: the bn variants with one transform exponent for all channels
# (wb_adaptive_anscombe off, variants_xmp.py). TEMPLATE=... sets the
# history the variants are appended to (base_xmp.py output from session 10)
#
# writes <work>/<name>_{wall,bird,grass,rock}.png (each region plus a 300 px
# margin, crop_xmp.py), about 1.5 s per crop instead of 17 s per frame;
# pass <work>/<name> to tradeoff.py. bn renders run with DT_DN_BANDNOISE=1
# DT_DN_BNONCE=1 and the band noise fixed to the full frame's estimates for
# that strength (DT_DN_BNFIXED, measured once per strength and cached), so
# they match the full-frame render; the extra VAR=value switches are added
# to the environment. The strength must be one of the sweep values in
# variants_xmp.py. Expects bandnoise.patch applied and built in ../build
# (BUILD=... to override). WORK=... sets the work directory.
#
# Only modes whose thresholds are local (DT_DN_BNLOCAL) match the full frame
# this way: the whole-band BayesShrink rule, old mode included, takes the
# band variance from the crop. Compare those on full-frame renders.
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
raw=${RAW:-/c/temp/denoise/P1378616.RW2}
work=${WORK:-/tmp/dn-quick}
build=${BUILD:-$src/build}
pics=$HOME/Pictures/Darktable/20260430_no_name
template=${TEMPLATE:-$pics/20260430_0012.RW2.xmp}
name=$1 mode=$2 s=$3
shift 3
mkdir -p "$work/xmp"

[ -f "$work/xmp/sw_${mode}_s${s}.xmp" ] ||
  python3 "$here/variants_xmp.py" "$template" 2.176e-4 "$work/xmp"
x=$work/xmp/sw_${mode}_s$s
[ -f "$x.xmp" ] || { echo "no sweep variant $x.xmp" >&2; exit 1; }
[ -f "${x}_wall.xmp" ] || python3 "$here/crop_xmp.py" "$x.xmp" "$work/xmp"

cli() {
  local c
  c=$(mktemp -d)
  rm -f "$2"
  "$build/bin/darktable-cli" "$raw" "$1" "$2" --apply-custom-presets false \
    --core --configdir "$c" --library :memory: "${@:3}"
  rm -rf "$c"
}

envs=()
if [ "${mode#bn}" != "$mode" ]; then
  # DT_DN_DESPECK changes the data before the noise is measured, so the
  # estimates are cached per strength and despeck level
  pre=()
  for a in "$@"; do
    case $a in DT_DN_DESPECK=*) pre=("$a") ;; esac
  done
  fixed=$work/xmp/bnfixed_${mode}_s${s}${pre:+_${pre#DT_DN_}}.txt
  if [ ! -s "$fixed" ]; then
    cfg=$(mktemp -d)
    env DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 DT_DN_BANDNOISE_LOG=1 "${pre[@]}" \
      "$build/bin/darktable-cli" "$raw" "$x.xmp" "$work/xmp/full.png" \
      --apply-custom-presets false --core --configdir "$cfg" \
      --library :memory: 2>&1 | python3 -c '
import re, sys
v = []
for l in sys.stdin:
    m = re.search(r"scale-0 noise (\S+) (\S+) (\S+),", l) or \
        re.search(r"scale \d+ noise x strength (\S+) (\S+) (\S+)", l)
    if m:
        v += m.groups()
v = v[:24]
assert len(v) == 24, v
print(" ".join(v))' > "$fixed"
    rm -rf "$work/xmp/full.png" "$cfg"
  fi
  # the logged per-scale values are times strength: divide back out
  envs=(DT_DN_BANDNOISE=1 DT_DN_BNONCE=1 "DT_DN_BNFIXED=$(python3 -c "
v = open('$fixed').read().split()
print(' '.join(v[:3] + [str(float(t) / $s) for t in v[3:]]))")")
fi
for r in wall bird grass rock; do
  (
    [ ${#envs[@]} -gt 0 ] && export "${envs[@]}"
    [ $# -gt 0 ] && export "$@"
    cli "${x}_$r.xmp" "$work/${name}_$r.png" \
      --conf plugins/imageio/format/png/bpp=16 >/dev/null 2>&1
  ) &
done
wait
