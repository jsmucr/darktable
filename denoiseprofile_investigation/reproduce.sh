#!/bin/bash
# re-run the measurements of sessions 2 and 3 on the ISO 20000 sample
#
#   ./reproduce.sh [raw] [workdir]
#
# needs a built tree in ../build; writes about 750 MB of PFMs into workdir
# and removes them at the end
set -e

here=$(cd "$(dirname "$0")" && pwd)
src=$(dirname "$here")
raw=${1:-/c/temp/denoise/P1378616.RW2}
work=${2:-/tmp/dn-investigation}
cli="$src/build/bin/darktable-cli"
mkdir -p "$work"

# interpolated DC-G9 ISO 20000 profile (data/noiseprofiles.json,
# dt_noiseprofile_interpolate between ISO 12800 and 25600)
A="3.526e-4 2.176e-4 3.202e-4"
B="1.23e-6 1.27e-6 1.04e-6"
# flat patch of the wall in P1378616 (x y w h)
PATCH="800 150 480 320"

render() {
  "$cli" "$raw" "$1" "$2" --apply-custom-presets false --core \
    --configdir "$work/cfg" --library :memory: \
    --conf plugins/lighttable/export/iccprofile=image \
    --conf plugins/lighttable/export/style=none >/dev/null 2>&1
}

gcc -O2 -o "$work/noiseprofile" "$src/tools/noise/noiseprofile.c" \
  -I"$src/build/src" $(pkg-config --cflags glib-2.0 gmodule-2.0) -lm

python3 "$here/profiling_xmp.py" "$src" "$work"
for t in ppg rcd cfa; do
  xmp="$work/prof_$t.xmp"
  [ $t = cfa ] && xmp="$work/cfa.xmp"
  render "$xmp" "$work/$t.pfm"
done

cd "$here"
for t in ppg rcd; do
  "$work/noiseprofile" "$work/$t.pfm" > "$work/$t.dat"
  echo "profiling-tool measurement with $t:"
  python3 profile_fit.py "$work/$t.dat" $A
done
echo "raw photosites:"
python3 raw_noise.py "$work/cfa.pfm" $PATCH $A $B
for t in rcd ppg; do
  echo "a-trous bands after $t, in units of the green profile sigma:"
  python3 bands.py "$work/$t.pfm" $PATCH 2.176e-4 1.27e-6
done

rm -rf "$work"/*.pfm "$work/cfg"
