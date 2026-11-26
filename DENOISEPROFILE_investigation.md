# denoise (profiled) on high-ISO Lumix G9 files: investigation notes

Working document for the follow-on agent. Records what was found, what was
verified from the tree or by measurement, and what is still speculation. Do
not treat as a design document.

Starting complaint: whatever is done with denoise (profiled), the result on
a noisy G9 file is clearly worse than the camera JPEG, which was shot with
in-camera noise reduction at its default (0).

## TL;DR

- **The G9 noise profile is not the problem.** Measured with darktable's own
  profiling tool and the PPG demosaic, the ISO 20000 sample comes out at
  0.86-1.24x the interpolated profile (session 2).
- **The raw data is plain white noise.** No sign of in-camera raw filtering:
  2x2 and 4x4 binning of a flat patch average the noise exactly as white
  noise would (session 2).
- **The module's per-scale noise model has about the right shape.** It
  expects the band sigma to fall by `varf` = 0.523 per a-trous scale, much
  slower than white noise (0.225); after demosaic the measured fall-off is
  close to the model (session 3). Session 2 claimed the opposite; that claim
  is **retracted**, do not build on it.
- **The noise level the module works with is too low.** Measured inside
  the module (session 5), the finest band carries 1.4-1.9x the noise the
  model expects in RGB mode, in every channel and at three brightness
  levels. Session 3 measured 1.8-2.5x for red and blue, but without white
  balance, which the module never sees (session 5).
- **Using the profile's red and blue entries makes it worse, not better.**
  Profiles are measured with white balance off before demosaic; the module
  gets white-balanced, demosaiced data, where green is the noisiest channel.
  Applying the per-channel entries widens the channel imbalance at all
  three levels (session 5). Round 1 TODO 2 is closed on that.
- **In Y0U0V0 mode (the default) luma carries about 5x the noise the
  model expects and chroma about 0.25x** (session 5). Demosaic correlates
  the noise across channels (0.5-0.74), which the matrix ignores, and the
  luma row is not unit-variance even under the module's own assumption. So
  the default luma threshold is about 0.3 sigma, which explains the
  leftover grain, and all chroma detail is discarded at every scale.
- **A uniform level correction is what the strength slider already does.**
  Strength around 2 removes the grain but softens fine detail and leaves
  **isolated dark single-pixel specks** in wavelet mode. The specks, not the
  noise estimate, are what keeps darktable behind the JPEG here (session 2).
- **The specks are the dark tail of the noise, made heavier by the
  variance-stabilizing transform and passed through by soft thresholding**
  (session 4). At this signal level the concave transform turns the input's
  bright-skewed noise into dark-skewed noise; 4-5 sigma dark outliers lose
  only the threshold (about 1.5 sigma) and come out as specks. The speck
  count follows the transform's exponent ("preserve shadows"): 30, 76, 201
  and 1297 at shadows 0, 0.5, 0.94 (inferred default) and 1.8. Photosites
  clipped to exactly 0 before the module add to it (26% of specks).
- **Workaround in the GUI:** lower "preserve shadows" to about 0.5 when
  raising strength in wavelet mode. Fewer specks, no visible detail loss
  on this file (session 4).
- **Best result so far:** raw denoise at threshold 0.02 followed by
  non-local means auto. No specks, clean flat areas, but feathers softer
  than in the JPEG (session 2).
- **Measuring the noise per band from the data fixes the Y0U0V0
  normalization** (session 6, experiment behind `DT_DN_BANDNOISE`): the
  finest band comes out at 1.05 / 0.86 / 0.94 instead of 5.2 / 0.26 / 0.25.
  At the JPEG's level of fine grain it keeps 9-12% more feather detail than
  the old mode, about half the gap to the JPEG, but plain BayesShrink then
  leaves coarse luma mottle; flooring the threshold at 1-1.5 sigma keeps
  most of the gain with mottle at or below the JPEG's.
- **Estimating BayesShrink's signal level locally instead of per band
  removes the mottle and keeps more detail** (session 7): at the JPEG's
  wall noise, bird detail is 0.20 against 0.15 for the old mode and 0.18
  for the JPEG, with the old mode's low mottle. What is left on flat areas
  and in texture is **specks**.
- **Wiener shrinkage on luma, a wider window and a despeck pass remove
  the specks** (session 8). Against old mode at 3.0: the same wall noise
  with 41% more feather detail (37% in session 9's properly exposed
  render) and no specks. Left: a grain halo a few pixels wide along
  strong edges, which the JPEG also has.
- **Against the JPEG, with this image's own white balance and matched
  brightness** (session 9): a cleaner wall, comparable rock texture, but
  the JPEG is crisper in the feathers and grass (0.179 against 0.139),
  with Vivid color and in-camera sharpening. Session 8's "more detail
  than the JPEG" was measured on renders 1.5 EV too dark and is
  **retracted**.
- **With capture sharpening (the user's normal sharpening) the measured
  mode adapts and old mode does not** (session 10): old mode's wall noise
  quadruples and its specks rise from 100 to 1361; the new mode gains
  detail at less noise. The rock speckle is a **tint that follows the luma
  texture**, because chroma detail is removed while luma detail is kept.
  One transform exponent for all channels plus luma-guided chroma detail
  brings it to the JPEG's level.
- **On 79 holiday images (session 11) the new mode only pays off from
  about ISO 400 up.** At ISO 200 it keeps 95% of the texture where old
  mode at its defaults keeps 99% at the same noise. At ISO 250-1000 it
  removes much more noise and all specks for 5-10% less texture; at ISO
  6400 and up it removes the specks and leaves flat areas cleaner than
  the JPEG. At ISO 25600 it washes out color in texture.
- **The noise's per-scale shape is the same on every image from ISO 640
  up, with or without capture sharpening** (session 12); at ISO 200 the
  estimate counts structure as noise. Capping it at that shape helps only
  a little. The bigger cause of the ISO 200 texture loss is the local
  shrinkage itself, which at low noise attenuates most texture, where old
  mode's small soft threshold leaves it untouched. So below about ISO 400
  the new mode should do less than old mode, and a real mode needs a
  noise-dependent strength or rule.
- **Most of the remaining gap was "preserve shadows" 0.5**, used since
  session 4 (session 13). With darktable's value inferred from the
  profile, flat areas are far cleaner for the same texture at every ISO;
  at ISO 6400+ the new mode beats the JPEG on flat-area noise and fine
  texture, at ISO 200 it is 4 points of texture behind old mode instead
  of 5-9. A gentler luma rule (soft threshold) did not help.
- **In the user's own workflow the new mode loses to both learned
  denoisers** (session 14): at the same flat-area noise, darktable's raw
  neural denoise keeps more mid-scale texture at every ISO and Topaz
  more still at high ISO. The new mode also leaves colored specks in
  dark textured areas, cause not found yet. It still beats old mode and
  the user's chroma-only preset at high ISO.

## Samples

- `/c/temp/denoise/P1378616.RW2` and the camera `.JPG`: DC-G9, ISO 20000,
  1/1000 f/6.3 +0.33 EV, Cloudy WB, Vivid, JPEG NR "Standard" (0). Bird on a
  rock, flat grey wall at the top. The main sample.
- `~/Pictures/Darktable/20260430_no_name/20260430_0012.RW2`: DC-G9, ISO 200,
  in-camera NR -5, forest with deep shadows.

The JPEG is a full 5184x3888 camera render. The RW2s only embed a
1920x1440 preview, which is too small and too compressed to compare noise
against (session 1).

Flat patch used for all measurements on P1378616: x 800, y 150, 480x320 px
(top-left of the wall). 100% crop regions used for visual comparison:
wall `360x260+1900+500`, bird `360x260+2050+2050`, grass `360x260+600+3300`.

Interpolated ISO 20000 profile (`dt_noiseprofile_interpolate`,
`src/common/noiseprofiles.c:377`, linear between the ISO 12800 and 25600
entries of `data/noiseprofiles.json`):
a = [3.526e-4, 2.176e-4, 3.202e-4], b = [1.23e-6, 1.27e-6, 1.04e-6].

## Tools in this branch

`denoiseprofile_investigation/`, pure python 3 (no numpy on this machine)
plus ImageMagick and the built `darktable-cli`:

- `reproduce.sh` re-runs every measurement of sessions 2 and 3 in about 20 s
  and prints the numbers quoted below.
- `specks.sh` re-runs session 4 in about 45 s: it applies
  `instrumentation.patch` to `src/iop/denoiseprofile.c`, rebuilds the
  module, renders with the module's buffers dumped, runs `specks.py` and
  `tails.py`, and reverts the patch on exit.
- `instrumentation.patch`: with `DT_DN_DUMP=<dir>` and
  `DT_DN_CROP="x y w h"` set, the wavelet path of the export pipe writes a
  crop of its input, the transformed image, every detail band, the residue,
  the synthesis before the backtransform and its output as float PFMs, and
  prints the transform parameters and per-scale thresholds to stderr.
- `specks.py` finds specks in a dumped output and traces each back through
  input, transform and the finest detail band. `tails.py` measures the
  asymmetry of the noise tails before and after the transform (its labels
  say Y0/U0/V0; in RGB mode the channels are R, G, B).
- `perchannel.sh` re-runs session 5 in under 2 minutes: it applies
  `perchannel.patch` and `instrumentation.patch`, dumps three flat patches
  with the per-channel switch off and on, runs `detail_noise.py` (noise per
  channel and scale in the module's own detail bands, and the
  cross-channel correlation), repeats the RCD export with and without white
  balance, and restores the source on exit.
- `quick.sh` renders only the `tradeoff.py` regions of P1378616 as a
  crop set (session 8; wall, bird, grass, and rock from session 10), in
  4-10 s per variant; `crop_xmp.py` writes the cropped histories, and
  `tradeoff.py` takes a crop set's prefix in place of a render (`--rock`
  adds the rock columns). `session8.sh` re-runs session 8 with it in
  about 5 minutes.
- `base_xmp.py` writes the base history from session 9 on: this image's
  own white balance, matched exposure, optionally demosaic capture
  sharpening. `session10.sh` re-runs session 10 in about 9 minutes.
- `perchannel.patch`: the session 5 experiment, switched on with
  `DT_DN_PERCHANNEL=1`; bit-identical output when off.
- `bandnoise.sh` re-runs sessions 6 and 7 in about 20 minutes: it renders four
  references with the clean module, applies `bandnoise.patch`, checks they
  are unchanged with the switches off, renders the strength sweeps and
  variants at 16 bit, prints `tradeoff.py` for all of them, the per-scale
  estimates and thresholds, and the wall's own band noise, and restores the
  source on exit. Leaves about 3.3 GB of renders in its work directory.
- `workflow.py` renders the user's own histories with denoise off and
  with the new mode in place of their denoise entry, and compares them
  with their default, neural and Topaz exports by spatial band (session
  14).
- `holiday_cmp.py` compares holiday.py variants by spatial band, flat
  against textured tiles (session 13).
- `shape_log.py` logs the per-scale noise estimates on holiday.py's
  images; `holiday_bands.py` splits their tiles' lightness into spatial
  bands (session 12). `shape_g9_cs.json` and `shape_g9_nocs.json` hold
  the logged estimates, with and without capture sharpening.
- `holiday.py` runs a set of raws with their camera JPEGs: tiles chosen
  automatically, exposure matched by bisection, old mode, new mode at
  several strengths and named variants (session 11); `holiday_summary.py`
  reports by ISO band.
- `bandnoise.patch`: the session 6-13 experiments (`DT_DN_BANDNOISE=1`
  and the variant switches listed there); bit-identical output when off. It
  carries its own copy of the detail-band dump, so do not stack
  `instrumentation.patch` on it.
- `tradeoff.py` prints wall noise, bird detail, wall chroma, wall mottle
  and speck counts on the wall and grass for 16-bit renders of P1378616
  (definitions in its header).
- `profiling_xmp.py` writes `tools/noise/profiling-shot.xmp` variants with an
  explicit demosaic entry: PPG, RCD, and passthrough monochrome (`cfa.xmp`,
  one raw photosite value per pixel). The stock XMP has no demosaic entry,
  so it measures with whatever the current default is (RCD).
- `profile_fit.py` fits var = a x + b to `tools/noise/noiseprofile.c` output
  the way `darktable-gen-noiseprofile` does. The tool builds standalone:
  `gcc -O2 tools/noise/noiseprofile.c -Ibuild/src $(pkg-config --cflags
  glib-2.0 gmodule-2.0) -lm`.
- `raw_noise.py` gives per-CFA-phase sigma, binning ratios and the share of
  photosites at or below black level.
- `bands.py` gives the noise per a-trous scale in the units the module
  assumes, plus the analytic white-noise ratios for the 5-tap filter.
- `variants_xmp.py` appends denoise (profiled) / raw denoise entries to a
  history (params layouts for denoiseprofile v12 and rawdenoise v2 are in
  the script). Render with
  `darktable-cli <raw> <xmp> <out> --apply-custom-presets false --core
  --configdir <tmp> --library :memory:`.

Builds: the scripts use `build/`, rebuilt from this branch in session 4.
Rebuild it in full after switching branches; a single module built against
another branch's headers need not match the rest of the tree.

Caveat for every render comparison so far: the template history is the
scene-referred default of 20260430_0012, so white balance and color
calibration are that image's (green cast on P1378616) and there is no
sharpening. The JPEG has Vivid and in-camera sharpening. Compare noise
and detail, not color. `--dump-pfm denoiseprofile` produces nothing from
`darktable-cli`: `debug_dump_PFM` only fires for the full (darkroom) pipe.

## Session 1: ISO 200, nothing was denoising

- All 113 local RW2s are DC-G9 at ISO 200 with in-camera NR -5. None of the
  71 edited XMPs has denoise (profiled), raw denoise or any other denoise
  module in its history. darktable does not auto-apply denoise (profiled),
  so those edits had no noise reduction at all.
- On 20260430_0012 the defaults (wavelets, Y0U0V0) remove the shadow chroma
  speckle almost entirely; fine luma grain stays. Non-local means auto is
  weak at ISO 200: the inferred patch radius is 1 and scattering 0.012
  (`infer_*_from_profile`, `denoiseprofile.c:2637-2655`).

## Session 2: ISO 20000, the profile holds and the raw is white

Profiling-tool measurement on the whole frame, ratio of fitted a to the
interpolated profile:

| demosaic | R | G | B |
|---|---|---|---|
| PPG | 1.24 | 0.86 | 0.99 |
| RCD | 0.79 | 0.52 | 0.69 |

So the G9 profile matches this file under PPG, which suggests (not verified)
that it was profiled when PPG was the default. With RCD the same measurement
reads about half in green, i.e. the profiling convention depends on the
demosaicer. A real scene is not a profiling target, so texture can only
inflate these fits, so it cannot explain the readings below 1.

Raw photosites on the flat patch (`raw_noise.py`):

| CFA phase | mean | sigma | 2x2 bin | 4x4 bin | <= 0 |
|---|---|---|---|---|---|
| (0,0) | 0.0112 | 0.00620 | 0.253 | 0.0612 | 3.3% |
| (0,1) | 0.0306 | 0.00916 | 0.243 | 0.0618 | 0.1% |
| (1,0) | 0.0305 | 0.00916 | 0.234 | 0.0657 | 0.0% |
| (1,1) | 0.0188 | 0.00746 | 0.253 | 0.0623 | 0.6% |

White noise gives 0.25 and 0.0625. Phase (0,0) has the lowest mean and is
presumably red; the CFA layout was not read from metadata. The photosite
sigmas are 2.7-3.3x the profile's sigma at the same level. That compares
photosites with a profile measured after demosaic, so it is a different
convention, not a contradiction.

Renders (100% crops, brightness-matched):

- defaults (wavelets, Y0U0V0, strength 1): far noisier than the JPEG on the
  wall, coarse grain and blotches.
- strength 2, chroma curve 0.8, luma 0.6: grain mostly gone, fine detail
  softer, isolated dark single-pixel specks across the wall. The specks
  appear with RCD, PPG, AMaZE and LMMSE, and with raw denoise 0.02 in front.
  Raw denoise 0.05 in front leaves fewer, but flat areas break up into
  large patches.
- non-local means auto: no specks, smooth, low-frequency mottle, softer
  feathers. Gain ("adjust autoset parameters") 3 changes little.
- raw denoise 0.02 + non-local means auto: best so far, clean wall, no
  specks, feathers still softer than the JPEG.

Specks against clipped photosites: on the strength-2 render, pixels darker than
0.65-0.85x their 5x5 median have a photosite at or below 0 within 3x3 in 7-10%
of cases, against 3% for random pixels. Some association, but it does not
explain the specks. Note that `precondition_v2` clamps negative input to 0
before the transform (`denoiseprofile.c:1013`). Session 4 measures the clipping
at the module input instead and finds a larger share.

Retracted: session 2 also compared block averages after demosaic against
white noise, found the noise 1.6-2.5x stronger at 2-8 px than white noise,
and concluded that the wavelet model, assumed to be white, underestimates
coarse-scale noise. The measurement stands; the conclusion does not,
because the model is not white (session 3).

## Session 3: the model is not white, the level is low

`variance_stabilizing_xform` (`denoiseprofile.c:1348`) and the loop in
`process_wavelets` (`:1564`) expect sigma_band = varf^scale with
varf = sqrt(70)/16 = 0.523, after a transform that normalizes the noise to
sigma 1 with the green profile entry. For the linear 5-tap a-trous transform,
white noise falls much faster (analytic, `bands.py`).

Band sigma on the flat patch, in units of sqrt(a_G x + b_G) at the patch
mean, which is what the module normalizes to:

| | s0 | s1 | s2 | s3 |
|---|---|---|---|---|
| white noise (relative to s0) | 1.000 | 0.225 | 0.096 | 0.046 |
| module expects | 1.00 | 0.52 | 0.27 | 0.14 |
| RCD R | 2.52 | 0.94 | 0.49 | 0.26 |
| RCD G | 1.75 | 0.86 | 0.40 | 0.20 |
| RCD B | 2.24 | 0.93 | 0.50 | 0.27 |
| PPG R | 2.70 | 1.05 | 0.54 | 0.27 |
| PPG G | 1.94 | 0.79 | 0.40 | 0.20 |
| PPG B | 2.47 | 1.05 | 0.55 | 0.29 |

- Measured / expected per scale: green 1.75, 1.64, 1.46, 1.40; red 2.52,
  1.80, 1.79, 1.82; blue 2.24, 1.78, 1.83, 1.89 (RCD). The shape is close to
  the model; the level is off by a roughly constant factor per channel.
- The red and blue excess over green (1.44x and 1.28x at s0) is in the
  direction of the profile's own R/B entries, which the module ignores:
  sqrt(a_R/a_G) = 1.27, sqrt(a_B/a_G) = 1.21. **Superseded by session 5:**
  these exports demosaic without white balance, as the profiling XMP does.
  With the image's white balance applied before demosaic, as in a normal
  pipeline, red and blue come out below green.
- The module's empirical factors already push the other way:
  `adjt` = 8 "because it seemed a little weak" (`:1375`) and 2.5x strength
  in Y0U0V0 mode (`:1514`). How much of the measured gap they absorb has not
  been worked out.
- Hypothesis, not verified: the profiling tool estimates noise from the
  finest diagonal Haar coefficient of a demosaiced image
  (`tools/noise/noiseprofile.c`), where demosaic suppresses noise most, so
  profiles systematically read below the per-pixel noise the module then
  sees. That would affect every camera, not only the G9.

A per-scale correction (estimate each band's noise from the data and
correct the model's shape) was designed and then dropped before any code
was written, since the shape is already about right.

## Session 4: the specks are the transformed noise's dark tail

Traced with `specks.sh` on the strength-2 render (strength 2, chroma curve
0.8, luma 0.6, Y0U0V0) in the wall crop `360x260+1900+500`. Transform
parameters printed by the instrumented module for this image:
p = [0.855, 0.943, 0.883] (`shadows` 0.943 plus the white-balance term),
compensate_p 0.844, bias -0.784, a single 5184x3888 ROI (no tiling).

The trace, speck by speck (201 specks: output luminance below 0.65x its
5x5 median, in 91136 pixels):

- Every speck is already a dark outlier going in: median z = -3.59 in input
  luminance against the local median.
- After `precondition_Y0U0V0` (`denoiseprofile.c:1128`) all 201 sit below
  -3 sigma in Y0, median -4.47.
- In the finest detail band their Y0 coefficients are -2.5 to -3.7 times
  the threshold. The threshold is 1.56x the band's robust sigma, and soft
  thresholding (`accumulate`, `src/common/eaw.c:24`) only subtracts it, so
  they survive at 1.5-2.7 thresholds and come out as specks.

Why the tail is dark: the transform f(x) = c (x + b)^(1 - p/2) is concave
(exponent 0.53-0.57 here), which stretches values below the local level and
compresses those above. At the wall's level the noise going into the module is
about 40% of the signal in red, far outside the small-noise regime the
transform's Taylor argument assumes (comment above `precondition_v2`), so the
stretch is strong. Share of residuals beyond 3 and 4 sigma (Gaussian: 0.13% and
0.003% each side):

| buffer | < -3 s | > +3 s | < -4 s | > +4 s |
|---|---|---|---|---|
| input R | 0.04% | 0.82% | 0.00% | 0.12% |
| input G | 0.26% | 0.97% | 0.01% | 0.13% |
| input B | 0.37% | 0.65% | 0.02% | 0.09% |
| transformed Y0 | 0.75% | 0.36% | 0.07% | 0.03% |
| transformed U0 | 2.26% | 0.23% | 0.46% | 0.01% |
| transformed V0 | 1.98% | 0.36% | 0.47% | 0.01% |

The input noise is skewed bright, as photon noise at low counts is; after
the transform it is skewed dark.

Intervention, same render with only `shadows` changed (the exponent is
1 - p/2 with p = shadows plus the white-balance term, clamped at 0):

| shadows | specks | Y0 < -4 s | Y0 > +4 s |
|---|---|---|---|
| 0 (linear transform) | 30 | 0.00% | 0.11% |
| 0.5 | 76 | 0.01% | 0.07% |
| 0.94 (inferred default) | 201 | 0.07% | 0.03% |
| 1.8 | 1297 | 2.19% | 0.00% |

At shadows 0 the remaining specks are mostly bright ones, from the
untransformed bright tail. Visually, shadows 0.5 and 0 remove most dark
specks with no visible loss of feather detail against 0.94.

Clipping adds to it: 26% of the specks have an input channel at exactly 0,
against 0.8% of random pixels (in the crop, 0.62% of input red pixels are
exactly 0 and none are negative). The raw data has negatives (session 2); RCD
clamps its output at 0 (`src/iop/demosaicing/rcd.c:402-404`) and the transform
clamps `in + b` at 0 again (`denoiseprofile.c:1149`, `:1155`). A clipped
photosite maps to the lowest value the transform can produce, which is the far
end of the dark tail.

RGB mode (`wav_strong_rgb`) leaves only 5 specks, but the render is flat
and patchy with most fine detail gone (bird crop), so it hides the specks
by overdenoising rather than avoiding them. Its transformed red is just as
dark-skewed (2.44% below -3 sigma).

Side observation, not yet understood: in Y0U0V0 mode at strength 2 the
chroma (U0, V0) thresholds run from 20479 at scale 0 to 8.6 at scale 6.
At every scale the observed chroma detail variance is below the variance
the model expects (0.034 against 1 at scale 0), so `std_x` hits its 1e-6
floor (`:1370-1372`) and all chroma detail is discarded; the chroma comes
from the residue alone.
Belongs with TODO 2, since it is a noise-level question.

## Session 5: per-channel profile entries do not fit the module

Experiment: `perchannel.patch` passes the profile's a and b per channel to
the RGB-mode and non-local means transforms, and in Y0U0V0 mode weights the
conversion matrix by sqrt(a_c / a_G) instead, keeping one transform gain so
U0 and V0 still cancel the signal (`set_up_conversion_matrices`,
`denoiseprofile.c:1291`). It is switched on with `DT_DN_PERCHANNEL=1`.
Switched off, its output is bit-identical to the unpatched module for
wavelets Y0U0V0, wavelets RGB, strength 2 and non-local means auto. The
OpenCL side is changed to match but was only compiled: this machine has no
OpenCL device (WSL2, see What is not claimed here).

Noise of the finest detail band inside the module (`detail_noise.py` on
the instrumented dumps, wavelets RGB at strength 1; the model expects 1.0
in every channel):

| patch (input mean R G B) | switch | R | G | B |
|---|---|---|---|---|
| wall 800,150 480x320 | off | 1.52 | 1.91 | 1.62 |
| | on | 1.20 | 1.91 | 1.34 |
| mid 3100,850 480x200 (0.036 0.043 0.045) | off | 1.41 | 1.83 | 1.53 |
| | on | 1.11 | 1.83 | 1.26 |
| bright 3100,1290 480x150 (0.085 0.095 0.102) | off | 1.38 | 1.79 | 1.50 |
| | on | 1.08 | 1.79 | 1.24 |

Inside the module green is the noisiest channel at every level, and the
per-channel entries lower red and blue further. By scale 1 the channels are
within 10% of each other with the switch off.

Why session 3 pointed the other way: the profiling XMP sets white balance
to 1, 1, 1, so the profile and every session 2-3 export were demosaiced
without white balance. The same RCD export with this image's white balance
(2.414, 1, 1.828) applied before demosaic, then divided back out, gives
R 1.46, G 1.76, B 1.56 at scale 0 against R 2.52, G 1.75, B 2.24 without it,
matching the module's own numbers. RCD does not treat channels
independently of their scaling, so the per-channel noise after demosaic
depends on the white balance, and the profile's R and B entries describe a
pipeline the module never sees.

Y0U0V0 mode (strength 1, same instrumented dumps):

| patch | Y0 | U0 | V0 |
|---|---|---|---|
| wall | 5.21 | 0.26 | 0.25 |
| mid | 4.99 | 0.24 | 0.24 |
| bright | 4.86 | 0.24 | 0.23 |

The model expects 1.0 for all three. Two causes, both measured or read:

- Demosaic correlates the noise across channels: in RGB-mode detail_0 the
  correlation is RG 0.69-0.71, RB 0.52-0.55, GB 0.72-0.74 at the three
  levels. The matrix variances assume independent channels, so the sum
  (Y0) is underestimated and the differences (U0, V0) overestimated.
- The Y0 row is not unit-variance even under the module's assumption that
  each channel's noise std is its white balance factor. The comment above
  it asks for var(sqrt(3) Y0) = 1, but the code multiplies by the sum of
  1/wb (`denoiseprofile.c:1311`) where a weighted mean would divide by it.
  For this image the row gives std 3S/2.5 = 2.35 (S = sum of 1/wb = 1.961,
  2.5 = the Y0U0V0 strength compensation, `:1514`); dividing would give
  0.61. Whether this is a bug or an intended scale later tuned around by
  the 2.5 is not known; the 2.5 comment says the mode "was much less
  denoised" without it.

Consequences at the default strength: the scale-0 luma threshold is 1.59
against a measured luma noise of 5.2, i.e. 0.3 sigma, so soft thresholding
barely touches the luma grain. The chroma variance is below the model's
noise variance at every scale, so the BayesShrink threshold hits its floor
(8000 at scale 0) and all chroma detail is dropped; chroma comes from the
coarsest residue alone.

## Session 6: measured band noise normalizes Y0U0V0, detail gain is modest

Experiment (`bandnoise.patch`, `DT_DN_BANDNOISE=1`, wavelets with the new
transform, CPU only; `process_cl` returns `DT_OPENCL_PROCESS_CL` so the
pipe falls back to the CPU): instead of the model, the noise of each band
is measured from the data. `_band_noise` takes the mean square of the band
in blocks (16 px at scale 0, doubling per scale, shrunk until there are at
least 64 blocks) and uses the 10th percentile across blocks, so texture
and edges do not count. The finest band, measured once before the loop,
sets a per-channel gain that brings Y0, U0 and V0 to unit noise; the gain
is multiplied back out after the residue is added. At each scale the
BayesShrink threshold then uses the measured sigma times strength, with
the extra factor 8 (`adjt`) dropped. Switched off, output is bit-identical
to the unpatched module (PFM `cmp`) for wavelets Y0U0V0, wavelets RGB,
strength 2 and non-local means auto. Variants, all behind more switches:

- `DT_DN_BNONCE=1`: strength in the thresholds only. Without it strength
  also enters the gain, so the threshold goes with strength squared.
- `DT_DN_BNKMIN=k`: threshold at least k times the measured band sigma.
- `DT_DN_BNK=k`: threshold exactly k times the measured band sigma.
- `DT_DN_BNFLOOR=1` / `DT_DN_BNGAIN=1`: band sigma at least / exactly the
  model's `varf^scale`, i.e. measured gain with model-shaped thresholds.
- `DT_DN_BANDNOISE_LOG=1`, `DT_DN_THRLOG=1`: estimates and thresholds.

Normalization works. Noise of the module's own detail bands on the wall
(`detail_noise.py`, strength 1.25 once; model expects 1.0 at scale 0):

| scale | Y0 | U0 | V0 | model |
|---|---|---|---|---|
| 0 | 1.05 | 0.86 | 0.94 | 1.00 |
| 1 | 0.41 | 0.78 | 0.83 | 0.52 |
| 2 | 0.18 | 0.49 | 0.53 | 0.27 |
| 3 | 0.10 | 0.26 | 0.30 | 0.14 |

against 5.21 / 0.26 / 0.25 at scale 0 in session 5. The whole-frame
estimates are within 14% of the wall's values at scale 0 and 4-11% below
them at scales 1-3. Luma falls off faster than the model and chroma
slower, which is the demosaic correlation of session 5 again.

Metrics (`tradeoff.py`, 16-bit renders, chroma 0.8 for the old mode and
1.0 for the measured mode, shadows 0.5 for both): wall noise is the luma
high-pass (sigma 6) RMS over mean on the wall, bird detail the same on the
feathers, wall mottle the 2-16 px luma band on the wall, wall chroma the
spread of Lab a, b. Interpolated linearly to the JPEG's wall noise
(0.0187) along each strength sweep:

| mode | bird detail | wall mottle | wall chroma |
|---|---|---|---|
| old (strength 2-3) | 0.152 | 0.0030 | 0.148 |
| measured, once (1.25-1.5) | 0.169 | 0.0141 | 0.139 |
| measured, floor 1 sigma (1.0-1.25) | 0.170 | 0.0093 | 0.133 |
| measured, floor 1.5 sigma (1.0-1.25) | 0.165 | 0.0057 | 0.133 |
| measured, fixed k (2.5-3) | 0.145 | 0.0030 | 0.605 |
| camera JPEG | 0.179 | 0.0100 | (other colors) |

So at equal fine-grain noise the measured mode keeps 9-12% more feather
high-pass than the old one, about half the gap to the JPEG, with similar
chroma noise. It pays in mottle: plain BayesShrink leaves 5x the old mode's
2-16 px luma blotches, clearly visible on the wall. A floor of 1-1.5 sigma
on the threshold brings that to 2-3x, at or below the JPEG's, for most of
the detail gain. A fixed k-sigma threshold loses on every count.

Why the mottle (`DT_DN_THRLOG`, strength 1.25 once): BayesShrink's
threshold sigma_n^2 / sigma_x uses the variance of the whole band, so at
scales 2-4, where image structure dominates the band variance, the luma
threshold falls to 0.34-0.5 of the band's noise sigma and the coarse grain
passes. At scale 0 luma, and chroma at scales 0-3, the band variance is
below the noise estimate, sigma_x hits its 1e-3 floor and the band is
removed outright; chroma scale 4 gets about 19 sigma. The old mode at
strength 3 has luma thresholds of 2.7-4.9 sigma at scales 0-3 (against
its own dumped band noise), hence no mottle and the softer feathers.

The model-shaped variants are not usable: wall noise drops from 0.043 to
0.002 between strength 1.0 and 1.25 (mfloor), and model-only leaves 0.95
chroma at 1.0. Not investigated further.

Visual check (`floor2.png` montage, not kept: wall and bird crops of the
JPEG, old 3.0, measured 1.25 once, and floor 1 and 1.5 sigma, renders
lifted x2.7 for viewing): the measured renders keep visibly more texture
in the rock and feathers than old 3.0; plain measured shows wall blotches,
floor 1.5 sigma is nearly as clean as old 3.0. None matches the JPEG's
feather contrast, which also has in-camera sharpening.

Caveats: one file, one wall, one bird crop; linear interpolation between
sweep points; the bird metric counts leftover noise as detail; all CPU.

## Session 7: local thresholds remove the mottle, specks are what is left

Added to `bandnoise.patch`, on top of the measured band noise:

- `DT_DN_BNLOCAL=r`: BayesShrink with sigma_x estimated per coefficient,
  from a box mean of the band's squared coefficients (`dt_box_mean`) with
  radius r << scale (capped at a quarter of the image side), instead of
  the whole band. The numerator is the whole-band rule's, so only sigma_x
  changes. Synthesis is done in place of `eaw_synthesize` with the same
  soft threshold.
- `DT_DN_BNLOO=1`: leave the coefficient itself out of its window's mean.
  Without it, a large outlier raises its own window's variance, which
  lowers its own threshold.
- `DT_DN_BNLKMIN=k`: per-coefficient threshold at least k times the
  band's noise sigma.

All with `DT_DN_BNONCE=1`. Switched off, output is still bit-identical to
the unpatched module (same four variants, PFM `cmp`), and session 6's
floor render is unchanged to the pixel.

`tradeoff.py` gains two columns: specks, the number of wall pixels more
than 10% of the mean off their 5x5 median, and the same on the grass crop.
The grass count includes texture: the JPEG has 1954 there and 30 on the
wall.

| render | wall noise | bird detail | wall chroma | wall mottle | specks | grass specks |
|---|---|---|---|---|---|---|
| old 3.0 | 0.0085 | 0.142 | 0.105 | 0.0020 | 169 | 204 |
| session 6, floor 1 sigma, 1.25 | 0.0154 | 0.168 | 0.119 | 0.0090 | 58 | 292 |
| local r4, 1.25 | 0.0068 | 0.193 | 0.103 | 0.0009 | 87 | 809 |
| local r4 LOO, 1.1 | 0.0165 | 0.200 | 0.126 | 0.0020 | 610 | 2542 |
| local r4 LOO, 1.15 | 0.0105 | 0.197 | 0.102 | 0.0013 | 263 | 1607 |
| local r4 LOO, 1.25 | 0.0034 | 0.192 | 0.085 | 0.0005 | 22 | 611 |
| local r2 LOO, 1.15 | 0.0219 | 0.197 | 0.169 | 0.0033 | 1001 | 2516 |
| camera JPEG | 0.0187 | 0.179 | (other colors) | 0.0100 | 30 | 1954 |

At the JPEG's wall noise, interpolated as in session 6: bird detail 0.201
for r4 LOO and 0.195 for r2 LOO, against 0.170 for the session 6 floor,
0.152 for the old mode and 0.179 for the JPEG. Mottle is 0.0023-0.0028,
down from 0.0093 and back at the old mode's 0.0030. Chroma is unchanged at
0.14-0.15.

The detail figure is inflated by specks, so it was repeated after a 3x3
median (speck-robust): bird 0.189 for r4 LOO at 1.1 (wall noise 0.0165),
0.163 for the session 6 floor, 0.171 for the JPEG and 0.139 for old 3.0.
The same median on the wall gives 0.0014 for r4 LOO at 1.1 against 0.0132
for the JPEG. Most of the wall noise the local mode leaves is specks: the
grain and mottle are gone.

Specks are now the limit. On the wall, r4 LOO needs strength 1.25 to get
them to the JPEG's level (22 against 30), and on the grass every local
variant has more than old 3.0, since texture lowers the local threshold
and the session 4 dark outliers pass with it. Visually (2x crops of the
feathers and grass, not kept), the local renders have the most feather
and grass texture of all darktable renders here, with scattered dark and
bright single-pixel specks in the grass; old 3.0 has few specks and no
texture. Leave-one-out lowers the specks at every setting (r4 at 1.25:
87 to 22 on the wall, 809 to 611 on the grass) and costs under 1% of
bird detail at the same strength. A
1 sigma floor (`BNLKMIN=1`) leaves the specks unchanged and costs 6% of
bird detail. r8 behaves like r4, with a steeper strength response.

Caveats as in session 6. The speck count is a 5x5-median test, which also
counts fine texture and is only comparable between renders of the same
crop.

## Session 8: Wiener shrinkage, wider windows and a despeck pass

Faster loop first: `quick.sh` renders only the three `tradeoff.py`
regions plus a 300 px margin (`crop_xmp.py` appends a crop to the
history; the pipe then processes only that region). A variant takes 4-10 s
instead of 17 s per frame, and sweeps run in parallel. The module's scale
count follows the full image (`denoiseprofile.c:917`), but the measured
band noise would come from the crop, so `DT_DN_BNFIXED` passes the full
frame's estimates in, measured once per strength and despeck level and
cached. With that, crop sets match full-frame renders within one unit of
the last printed digit in every `tradeoff.py` column (checked on eight
variants, r 4 to 16). This works only for local thresholds: the whole-band rule takes its
variance from the crop (old mode at 3.0 reads 0.0065 wall noise on crops
against 0.0085 on the frame).

New switches in `bandnoise.patch`, all on top of `DT_DN_BNLOCAL`:

- `DT_DN_BNLBO=b`: leave a block of radius b << scale out of the window
  instead of the coefficient alone. Demosaic spreads an outlier into a
  2-3 px blob (4x crops of the wall), whose other members still lowered
  the threshold under plain leave-one-out.
- `DT_DN_BNWIENER=1` (all channels) or `=y` (luma only): attenuate each
  coefficient by its local Wiener gain sx^2 / (sx^2 + sn^2) instead of soft
  thresholding. Soft thresholding keeps only the largest noise
  coefficients, which is what turns leftover noise into isolated specks.
  Wiener scales all of them down.
- `DT_DN_DESPECK=k`: before the decomposition, a value more than k finest-band
  sigmas beyond all 8 of its neighbors is pulled back to the nearest
  neighbor value. Lines and edges keep a neighbor on their own side. At
  strength 1.1, k = 2 touches 1.1% and k = 3 0.3% of the values.
- `DT_DN_BNFIXED`: see above.

Results (crop sets, strength in the name, all with leave-block-out 1
except the `loo` rows; `ds` is the despeck k):

| render | wall noise | bird detail | wall chroma | wall mottle | specks | grass specks |
|---|---|---|---|---|---|---|
| old 3.0 (full frame) | 0.0085 | 0.142 | 0.105 | 0.0020 | 169 | 204 |
| session 7, loo r4 1.1 | 0.0165 | 0.200 | 0.126 | 0.0020 | 610 | 2544 |
| loo r4 ds2 1.1 | 0.0128 | 0.200 | 0.106 | 0.0018 | 428 | 2003 |
| Wiener all r4 1.25 | 0.0082 | 0.192 | 0.348 | 0.0013 | 16 | 328 |
| Wiener luma r4 1.1 | 0.0186 | 0.200 | 0.133 | 0.0021 | 410 | 1957 |
| Wiener luma r4 1.2 | 0.0090 | 0.195 | 0.095 | 0.0010 | 45 | 597 |
| Wiener luma r8 1.1 | 0.0114 | 0.200 | 0.100 | 0.0009 | 43 | 1184 |
| Wiener luma r8 ds2 1.1 | 0.0094 | 0.200 | 0.095 | 0.0008 | 11 | 693 |
| Wiener luma r16 ds2 1.0 | 0.0246 | 0.206 | 0.147 | 0.0031 | 132 | 3395 |
| Wiener luma r16 ds2 1.1 | 0.0049 | 0.199 | 0.086 | 0.0004 | 0 | 359 |
| camera JPEG | 0.0187 | 0.179 | (other colors) | 0.0100 | 30 | 1954 |

What each step does:

- **Despeck alone** helps a little: at loo r4 1.1, wall specks drop from
  610 to 428 (k = 2) and 541 (k = 3), at no cost in bird detail. k = 2
  beats k = 3 at every radius tried.
- **Leave-block-out** alone barely moves anything (540 against 610).
- **Wiener on luma** leaves fewer specks at lower wall noise than soft
  thresholding: r4 at 1.2 has 45 on the wall and 597 on the grass at
  0.0090, soft thresholding (loo r4 1.15, session 7) 263 and 1607 at
  0.0105. On chroma it leaves about 4x the chroma noise, since soft
  thresholding removes the chroma bands outright (session 6); keep soft
  thresholding there.
- **Wider windows** lower the noise at the same strength and the same bird
  detail: at 1.1, wall noise 0.0186, 0.0140, 0.0114 and 0.0070 for r 4,
  6, 8 and 16, bird 0.199-0.200 throughout. On a flat area a wider window
  estimates the signal variance as zero more reliably; in the feathers
  the texture still fills it.

Best settings: Wiener on luma, leave-block-out 1, despeck 2, r 8 or 16,
strength 1.1. Against old mode at 3.0, r8 has about the same wall noise
with 41% more bird detail, under a tenth of the wall specks and less
mottle.
Against the JPEG it has half the wall noise, 12% more bird detail (no
sharpening on our side), a third of the wall specks and a tenth of the
mottle. r16 is cleaner still at the same detail.

Visually (2x crops of wall, feathers, grass and the branch edge, not
kept), r8 and r16 at 1.1 have clean walls, the feather and grass texture
of the session 7 renders, and no visible specks. r4 Wiener at 1.2 leaves
faint grainy patches on the wall where the small window overestimates
the signal. One thing stands out that no metric measures: a **grain halo
along strong edges**. Next to the branch against the bright background,
grain survives in a band a few pixels wide, since the window there takes
the edge's variance as signal. The JPEG has a similar band; old 3.0 has
none.

Open: the halo (an edge-aware or directional window would be the next
try), the steep strength response (wall noise falls 5x between 1.0 and
1.1 at r16), and everything from session 6's caveats.

## Session 9: a render with this image's own color, beside the JPEG

Every comparison up to session 8 used the template history, with another
image's color calibration (green cast) and about 1.5 EV darker than the
JPEG. For a fair look: keep only exposure, sigmoid and denoise (profiled)
from the template, let darktable insert its defaults for the rest (as-shot
white balance, no color calibration), and raise exposure from 0.7 to
2.9 EV, which matches the JPEG's mean on the wall (G 0.501 against 0.497)
and the bird (0.509 against 0.482). The white balance coefficients are
the same as the template's (2.414, 1, 1.828, the camera's Cloudy), so the
data denoise (profiled) sees does not change. (Checked after session 10:
the default white balance is "as shot" with "prepare data for color
calibration" on, `temperature.c:1729-1731`. With no color calibration
in the history, input color profile then rescales to the camera
reference coefficients (2.511, 1, 1.663; `colorin.c:910`, `-d pipe`
prints it), so the final color is camera reference, not as shot. Plain
as shot differs on the wall by 1 in L and 0.2 in a and b. Denoise
(profiled) runs before input color profile and sees the as-shot data
either way.) New mode: Wiener luma, r 8,
leave-block-out 1, despeck 2, strength 1.1. Old mode: strength 3, chroma
0.8, shadows 0.5.

| full frame | wall noise | bird detail | wall chroma | wall mottle | specks | grass specks |
|---|---|---|---|---|---|---|
| old 3.0 | 0.0063 | 0.101 | 0.199 | 0.0018 | 104 | 69 |
| new | 0.0066 | 0.139 | 0.175 | 0.0009 | 0 | 59 |
| camera JPEG | 0.0187 | 0.179 | 0.841 | 0.0100 | 30 | 1954 |

**Correction to session 8:** with matched brightness the JPEG has more
feather high-pass than the new mode (0.179 against 0.139), not 12% less.
The earlier figures were measured on renders 1.5 EV darker, where the
tone curve gives the same texture a different contrast relative to the
mean. Comparisons between darktable renders under the same history are
unaffected; comparisons with the JPEG before this session are not
reliable.

Visually (100% crops of the bird's head, the rock, the grass and the
wall):

- The new mode beats old mode everywhere: the rock keeps its grain
  structure instead of melting into blobs, grass blades and the feather
  pattern survive, and the wall is as clean.
- Against the JPEG: our wall is cleaner (the JPEG leaves visible fine
  grain), and the rock texture is comparable. The JPEG is crisper on
  the bird's head and the grass, has stronger color (Vivid) and visible
  sharpening; we have none.
- New issue: the rock shows dark blue-green speckle in its texture that
  the JPEG does not have. Session 10 shows it is a tint tied to the luma
  texture, not chroma noise as first guessed here.

The renders, the side-by-side and the 100% crops are in
`/c/temp/denoise/compare/` on this machine, with the history used.

## Session 10: capture sharpening, and the rock tint follows the luma

New base history (`base_xmp.py`): session 9's, optionally with the
demosaic module's capture sharpening at the values darktable autotunes
for this file (radius 0.53, threshold 0.45; `-d pipe` prints them). This
is the user's normal sharpening. Demosaic runs before denoise (profiled),
so the sharpening changes the noise the module sees. `quick.sh` takes
the base through `TEMPLATE`, the cached band noise is now keyed on the
transform too, and `tradeoff.py --rock` adds a rock region: the Lab a, b
spread in the 1-16 px band, and the correlation of a and b with L in
that band, i.e. color that follows the luma texture.

**Capture sharpening.** Old mode does not know about the sharpened noise:
at strength 3, wall noise goes from 0.0062 to 0.0241 and wall specks from
100 to 1361. The measured-noise mode adapts. At 1.2 with sharpening it
has wall noise 0.0042 and bird detail 0.144, against 0.0065 and 0.139 at
1.1 without, so sharpening first gives more detail at less noise. The gap
to the JPEG's 0.179 narrows to 0.146-0.156 for the variants below.

**The rock speckle is not chroma noise** (session 9 guessed it was). The
same render without denoise has corr(L, a) -0.13 to -0.22 on the rock,
the JPEG -0.15. The new mode has 0.87: the tint is tied to the luma
texture. Cause, in the transformed domain: for a surface of one color,
each channel's detail is its share of the luma detail, so U0 and V0
carry detail that is texture, not noise. The module removes nearly all
chroma detail (session 6) and keeps luma detail, so the backtransform
puts a texture-shaped tint on a neutral rock. The per-channel transform
exponents (from the white balance, `wb_adaptive_anscombe`, the
"whitebalance-adaptive transform" toggle) make it stronger: they bend the
channels differently, so even a gray surface has chroma detail.

Two fixes, both on top of session 8's setting (r 8, Wiener luma,
leave-block-out 1, despeck 2), on the sharpened base:

- **One exponent for all channels** (the toggle off; `bnw` in
  `quick.sh`): corr(L, a) 0.87 to 0.02, but corr(L, b) 0.30 to 0.81. The
  tint moves from teal to blue-gray and stays.
- **Luma-guided chroma detail** (`DT_DN_BNCGUIDE=1`): predict each chroma
  coefficient as luma detail times the coarse chroma-to-luma ratio at
  that pixel, shrink only the residual, and add the prediction back
  scaled by the denoised luma detail. With one exponent: 0.05 and 0.42,
  closest to the JPEG's -0.15 and 0.36. With per-channel exponents it
  overshoots (corr(L, a) -0.56), as expected when the channels are not
  bent alike.

| sharpened base | wall noise | bird detail | wall chroma | specks | grass specks | rock chroma | corr(L,a) | corr(L,b) |
|---|---|---|---|---|---|---|---|---|
| old 3.0 (full) | 0.0241 | 0.108 | 0.311 | 1361 | 1611 | 0.478 | 0.52 | 0.16 |
| old 3.0, one exponent (full) | 0.0054 | 0.087 | 0.126 | 74 | 104 | 0.316 | 0.21 | 0.41 |
| new 1.1 | 0.0109 | 0.150 | 0.160 | 41 | 973 | 0.942 | 0.87 | 0.29 |
| new 1.2 | 0.0042 | 0.144 | 0.128 | 0 | 250 | 0.920 | 0.87 | 0.30 |
| one exponent 1.2 | 0.0042 | 0.149 | 0.121 | 2 | 305 | 0.609 | 0.02 | 0.81 |
| guide, per-channel exp. 1.2 | 0.0042 | 0.149 | 0.127 | 0 | 413 | 0.579 | -0.56 | 0.64 |
| guide, one exponent 1.1 | 0.0111 | 0.153 | 0.158 | 39 | 2060 | 0.436 | 0.05 | 0.42 |
| guide, one exponent 1.2 | 0.0040 | 0.146 | 0.125 | 0 | 472 | 0.416 | 0.06 | 0.43 |
| no denoise | | | | | | | -0.13 to -0.22 | 0.12 to 0.28 |
| camera JPEG | 0.0187 | 0.179 | 0.841 | 30 | 1954 | 0.645 | -0.15 | 0.36 |

(The no-denoise row is from a 1 px and a 3 px pre-blur of the band; the
others use 1 px. The grass speck count rises with the guide because the
grass keeps more color texture, which the count includes.)

Visually (2x crops of rock, bird head and grass): with one exponent and
the guide the rock is neutral gray with a faint purple-blue variation,
like the JPEG's; session 8's setting gives teal speckle, one exponent
alone blue-gray speckle. Bird and grass are as in session 8, slightly
more colored. The JPEG still has more color in the grass and more
feather crispness.

The grass looks more olive than in session 9's render, but that is the
earlier renders drifting, not this one: mean Lab on the grass crop is
L 57.9, a -7.1, b 24.1 without denoise, a -8.4 to -8.9 and b 25.4-25.5
for old 3.0 and the session 8 setting, and a -7.4, b 24.2 with one
exponent and the guide. On the rock the session 8 setting moves a from
+0.63 to -0.57 (the teal), the guide leaves +0.30.

Side finding for stock darktable: with sharpening, old mode at 3.0 and
the "whitebalance-adaptive transform" toggle off has a quarter of the
wall noise, a twentieth of the wall specks and less rock tint, but 19%
less bird detail. The toggle changes how strength maps to the actual
noise level, so this is not a like-for-like comparison; a lower strength
with the toggle off was not tried.

Crop sets were checked against full frames again (guide, one exponent,
1.2: identical in every column but one grass speck). Switched off, the
patch is still bit-identical to the unpatched module; session 8's
setting renders unchanged.

## Session 11: 79 holiday images, ISO 200 to 25600

The user's holiday set (`C:\temp\denoise\holiday`, 370 G9 RW2 + JPG
pairs, Vivid, Cloudy WB; JPEG noise reduction "Standard", i.e. 0, on 175,
-5 on 195). Tested: all 39 above ISO 200 (ISO 250-1000: 35, ISO 6400,
20000 and two at 25600) and 40 random ISO 200 shots.

`holiday.py` does per image what sessions 9-10 did by hand, with no
hand-picked regions:

- tiles from the camera JPEG, 4x downscaled so noise does not count: the
  two flattest and the two most textured 360x260 tiles at mid brightness,
  away from the borders;
- exposure: the base history (`base_xmp.py`) gets the EV whose 1000 px
  render matches the JPEG's mean gray (bisection), then capture sharpening
  on and autotuned by darktable;
- renders: no denoise, old mode at its defaults for the ISO
  (`wav_default`, so what a user gets without touching it), and session
  10's setting (one exponent, r 8, Wiener luma, leave-block-out 1,
  despeck 2, guide) at strength 0.75, 0.9, 1.1 and 1.2;
- per tile: `tradeoff.py`'s high-pass RMS, specks, chroma and mottle.

`holiday_summary.py` reports per image and per ISO band: noise (flat
tiles), detail (textured tiles, relative to no denoise), specks, chroma.
About 1 minute per image and variant set; 79 images took 79 minutes,
the two extra strengths 33 more.

Medians per ISO band (noise = flat-tile high-pass over mean; detail =
textured-tile high-pass relative to no denoise):

| band | | JPEG | none | old default | new 0.75 | new 0.9 | new 1.1 | new 1.2 |
|---|---|---|---|---|---|---|---|---|
| 200 (40) | noise | 0.0047 | 0.0062 | 0.0042 | 0.0045 | 0.0040 | 0.0033 | 0.0030 |
| | detail | 1.47 | 1.00 | 0.99 | 0.95 | 0.93 | 0.92 | 0.91 |
| 250-500 (17) | noise | 0.0107 | 0.0197 | 0.0143 | 0.0113 | 0.0083 | 0.0047 | 0.0033 |
| | detail | 1.26 | 1.00 | 0.98 | 0.94 | 0.93 | 0.91 | 0.90 |
| 640-1000 (18) | noise | 0.0096 | 0.0277 | 0.0177 | 0.0163 | 0.0134 | 0.0084 | 0.0056 |
| | detail | 1.18 | 1.00 | 0.95 | 0.90 | 0.88 | 0.87 | 0.86 |
| | specks | 0 | 58 | 16 | 0 | 0 | 0 | 0 |
| 6400-25600 (4) | noise | 0.0200 | 0.0851 | 0.0620 | 0.0437 | 0.0315 | 0.0140 | 0.0095 |
| | detail | 0.66 | 1.00 | 0.86 | 0.67 | 0.58 | 0.49 | 0.46 |
| | specks | 166 | 15475 | 8441 | 3750 | 1312 | 51 | 5 |

What it says:

- **The JPEG's detail number is not comparable.** Above 1 at low ISO
  means its in-camera sharpening adds high-pass the raw does not have
  (1.47 at ISO 200). Only the darktable columns compare with each other.
- **ISO 200: the new mode costs texture for nothing.** Old mode at its
  defaults already reaches the JPEG's noise level with 99% of the
  texture; the new mode at the same noise (0.75) keeps 95%. Visually the
  ISO 200 tiles are hard to tell apart.
- **ISO 250-1000: the new mode removes much more noise and all specks,
  at 5-10% less texture.** Many of these are f/1.4 shots whose "textured"
  tiles are out-of-focus background, where much of the high-pass is
  noise; there the new mode and the JPEG are both smooth and old mode
  keeps grain (2x crops, `iso200_800_texture_zoom.jpg`). The detail
  number overstates the loss on such tiles; a noise-corrected version
  (subtracting the flat tiles' noise in quadrature) gave the same
  ranking, within 0.01-0.02.
- **ISO 6400 and up (4 images, P1378616 among them):** as in sessions
  8-10, specks go from thousands to tens and the flat areas get cleaner
  than the JPEG's. At the JPEG's noise level (strength about 1.0) the
  new mode keeps about 0.55 of the textured high-pass against the JPEG's
  0.66, which includes sharpening.
- **New problem at ISO 25600 (P1378610, P1378612): color loss.** The new
  mode washes out color variation in texture, such as purple leaves and
  green grass, which old mode (noisy) and the JPEG (Vivid) keep.
  Chroma detail is removed at all scales at this noise level (session 6),
  and the guide only restores chroma that follows luma texture. Not
  measured; seen in the tile montages.
- **Strength:** to match the JPEG's noise, the new mode needs about 0.75
  at ISO 200, 0.8-0.9 at 250-1000 and 1.0-1.1 at 6400 and up. The
  measured-noise mode was meant to make strength mean the same at every
  ISO, so this is a sign that its noise estimate is off at low ISO.

Why low ISO costs texture, tested on 20 images (10 at ISO 200, 10 at
640-1000), strength 0.9:

- Not despeck and not Wiener: turning off either or both changes detail
  by 0.01 at most.
- **The noise estimate.** The block 10th percentile counts faint
  structure as noise when the noise is low. At ISO 200 the estimated
  scale-1 luma noise is 0.54-0.77 of the finest band's (P1378441,
  P1378497, P1378726), against 0.36 where noise dominates (P1378616,
  ISO 20000, and P1378294, ISO 800); at scale 3, 0.21-0.26 against 0.09.
  Demosaic should give the noise the same shape at every ISO.
  `DT_DN_BNSHAPE` caps each band's estimate at P1378616's shape (min mode,
  `DT_DN_BNSHAPEMODE=set` replaces it): ISO 200 detail 0.93 to 0.96 at
  0.9 and 0.90 to 0.95 at 1.1, noise up by 15-20%. No change at 640-1000
  and above, where the estimate already has that shape.

Not done: a fixed shape is one camera and one demosaic; it would have to
come from the profile or from a measurement at a known noise level. The
color loss at very high ISO is unexplored. OpenCL, other cameras.

Montages for 8 images, the 2x texture crops and the per-image table are
in `C:\temp\denoise\compare\holiday\`. The renders are in
`/tmp/hol/run` (1.3 GB, tiles only).

## Session 12: the noise shape is fixed, the low-ISO loss is elsewhere

`shape_log.py` logs the per-scale noise estimates on every image, relative
to scale 0, with capture sharpening on and (28 images) off:

- **ISO 640 and up (22 images): one shape.** Scale-1 luma 0.379 of scale
  0, scale 2 0.187, scale 3 0.099 (chroma 0.72-0.76, 0.46-0.49,
  0.25-0.27), the 10%-90% range within a few percent at scales 1-2.
  Capture sharpening does not change it (identical to three decimals),
  nor does the image. ISO 6400+ adds noise at scales 4-6 that the others
  do not have, possibly low-frequency (pattern) noise; four images only.
- **ISO 200: scale-1 luma 0.57 median, 0.44-0.74 across images**, scale
  3 0.25. The estimate there includes image structure, as session 11
  suspected.

`DT_DN_BNSHAPEREL=1` makes `DT_DN_BNSHAPE` relative: each scale is capped
at the median shape above times this image's own scale-0 estimate, so it
needs no absolute level. On all 79 images, strength 0.9:

| ISO | | new 0.9 | shape cap 0.9 | old default |
|---|---|---|---|---|
| 200 | noise | 0.0040 | 0.0043 | 0.0042 |
| | detail | 0.93 | 0.95 | 0.99 |
| 250-500 | noise | 0.0083 | 0.0095 | 0.0143 |
| | detail | 0.93 | 0.93 | 0.98 |
| 640-1000 | | unchanged | | |

So the cap is right but small: at ISO 200 it trades a little noise for
two points of detail, and the new mode is still behind old mode.

What else was tried at ISO 200 (10 images, strength 0.75, old mode at
noise 0.0037, detail 0.987):

| variant | noise | detail |
|---|---|---|
| session 10 setting | 0.0039 | 0.945 |
| per-channel exponents | 0.0038 | 0.955 |
| no guide | 0.0039 | 0.939 |
| window r 4 | 0.0038 | 0.945 |
| no local thresholds (session 6 global BayesShrink) | 0.0044 | 0.949 |

None closes the gap, and session 11 already ruled out despeck and Wiener.

Where the texture goes (`holiday_bands.py`: Lab L energy per spatial
band, relative to no denoise, flat tiles | textured tiles):

| ISO | variant | fine 0-1 px | mid 1-3 px | coarse 3-8 px |
|---|---|---|---|---|
| 200 | old | 0.68 \| 1.00 | 0.62 \| 0.99 | 0.89 \| 1.00 |
| | new 0.75 | 0.69 \| 0.93 | 0.72 \| 0.94 | 0.87 \| 0.98 |
| | JPEG | 1.02 \| 1.24 | 0.94 \| 1.32 | 1.02 \| 1.21 |
| 250-500 | old | 0.71 \| 0.97 | 0.54 \| 0.98 | 0.63 \| 1.00 |
| | new 1.1 | 0.32 \| 0.69 | 0.24 \| 0.90 | 0.26 \| 0.97 |
| 640-1000 | old | 0.72 \| 0.88 | 0.53 \| 0.95 | 0.50 \| 0.99 |
| | new 1.1 | 0.33 \| 0.40 | 0.30 \| 0.86 | 0.37 \| 0.96 |
| | JPEG | 0.32 \| 0.68 | 0.49 \| 1.14 | 0.76 \| 1.15 |
| 6400+ | old | 0.78 \| 0.88 | 0.60 \| 0.87 | 0.69 \| 1.00 |
| | new 1.1 | 0.19 \| 0.24 | 0.22 \| 0.60 | 0.43 \| 0.85 |
| | JPEG | 0.21 \| 0.28 | 0.28 \| 0.74 | 0.60 \| 1.05 |

- **At ISO 200 old mode is the better design**: it takes the same share
  of the fine noise out of flat areas as the new mode and leaves texture
  untouched in every band. Its fine-scale luma threshold is a small
  fraction of the noise (session 5's misnormalization), and a small soft
  threshold barely touches coefficients well above it. The new mode's
  local rules (Wiener or soft, any window) shrink texture whose fine-band
  energy is only a few times the noise, which at ISO 200 is most
  texture.
- **The camera does no fine-scale noise reduction at ISO 200** (flat fine
  band 1.02); from ISO 640 it removes about as much fine noise as the new
  mode at 1.1 (0.32-0.33 against 0.33) and keeps more mid-band texture.
- At ISO 640-1000 the new mode's textured tiles lose 60% of the fine band,
  the JPEG's 32%. Many of these tiles are out-of-focus (session 11), so
  part of that is noise; the mid band (0.86 against 1.14 for the
  sharpened JPEG) is the safer comparison.

Conclusion for the defaults: below about ISO 400 the new mode should do
less than old mode, not more, and the strength that matches the JPEG
rises with ISO. A real mode would need an ISO- or noise-dependent
strength, or a gentler rule (a small fixed soft threshold) where the
noise is low. Not tried.

## Session 13: "preserve shadows" 0.5 was the hidden cost

Subset: the 10 ISO 200 and 10 ISO 640-1000 images of session 11 plus the
4 above ISO 6400. `holiday_cmp.py` prints, per variant, Lab L energy in
the fine (0-1 px) and mid (1-3 px) bands on flat | textured tiles,
relative to no denoise, plus flat-tile specks and chroma.

**A gentler luma rule does not help.** `DT_DN_BNLUMAK=k` replaces the
luma Wiener step with a soft threshold at k times the band noise
(`DT_DN_BNLUMAW=w` mixes the two). At ISO 200, k 0.5 gives flat 0.69 |
texture 0.90 in the fine band, the same trade as Wiener at 0.75 (0.70 |
0.91); larger k is worse on both. Old mode has 0.67 | 0.99.

**What does help: darktable's inferred "preserve shadows"** instead of
the 0.5 used since session 4. The new mode's sessions 6-12 all ran with
shadows 0.5 (chosen then to reduce old mode's specks). darktable infers
it from the profile (`infer_shadows_from_profile`, 1.34 at ISO 200, 0.94
at ISO 20000 for the G9). Same everything else (one exponent, r 8,
Wiener luma, leave-block-out 1, despeck 2, guide, shape cap), `bnwi` in
`variants_xmp.py`:

| ISO | variant | fine flat \| tex | mid flat \| tex | specks | chroma |
|---|---|---|---|---|---|
| 200 | old | 0.67 \| 0.99 | 0.55 \| 0.99 | 0 | 0.43 |
| | shadows 0.5, 1.1 | 0.53 \| 0.85 | 0.51 \| 0.90 | 0 | 0.45 |
| | inferred, 0.6 | 0.60 \| 0.95 | 0.59 \| 0.98 | 0 | 0.46 |
| | inferred, 1.0 | 0.11 \| 0.93 | 0.24 \| 0.97 | 0 | 0.42 |
| 640-1000 | old | 0.71 \| 0.88 | 0.52 \| 0.95 | 20 | 0.31 |
| | shadows 0.5, 1.1 | 0.29 \| 0.38 | 0.27 \| 0.84 | 0 | 0.26 |
| | inferred, 0.75 | 0.44 \| 0.67 | 0.38 \| 0.91 | 0 | 0.27 |
| | inferred, 1.0 | 0.10 \| 0.50 | 0.08 \| 0.87 | 0 | 0.25 |
| | JPEG | 0.32 \| 0.68 | 0.48 \| 1.13 | 0 | 0.47 |
| 6400+ | old | 0.78 \| 0.88 | 0.60 \| 0.87 | 8441 | 1.67 |
| | shadows 0.5, 1.1 | 0.19 \| 0.24 | 0.22 \| 0.60 | 51 | 0.90 |
| | inferred, 1.0 | 0.13 \| 0.43 | 0.11 \| 0.70 | 144 | 0.94 |
| | inferred, 1.1 | 0.06 \| 0.32 | 0.07 \| 0.65 | 29 | 0.92 |
| | JPEG | 0.21 \| 0.28 | 0.28 \| 0.74 | 166 | 1.39 |

- With the inferred value, flat areas get much cleaner for the same
  texture at every ISO: at ISO 200 and strength 1.0 the fine-band noise
  left in flat areas falls from 0.53 to 0.11 while texture keeps 0.93,
  and at ISO 6400+ the new mode keeps more fine texture than the JPEG
  (0.43 against 0.28) with less noise in flat areas (0.13 against 0.21).
- Most likely reason, not measured directly: with a transform exponent
  too far from the noise model, the transformed noise is not uniform
  across brightness, and a single measured level per band is wrong in
  darker or brighter parts. Specks, the reason for 0.5 in session 4, are
  now handled by despeck and Wiener (144 at strength 1.0, 29 at 1.1,
  against the JPEG's 166).
- ISO 200 is still the one band where old mode keeps the most texture
  at its flat-area noise (0.99 against 0.95 at strength 0.6), but the
  gap is down from 5-9 points to 4, and at strength 1.0 the new mode
  trades 6 points of texture for flat areas 6x cleaner.
- Visually (montage of 5 images, not kept): at ISO 25600 the inferred
  setting keeps more of the color in leaves and grass than shadows 0.5,
  so it explains part of session 11's color loss, but leaves fine dark
  grain in dark textured areas at strength 0.75-1.0. P1378616's feathers
  at 1.0 are closer to the JPEG than with shadows 0.5. The textured-tile
  fine band at high ISO still holds some leftover noise, so 0.43 against
  the JPEG's 0.28 overstates the texture kept. ISO 200 and 800 look alike in all
  variants at 100%.

Also changed: `holiday.py` writes full renders as uncompressed 16-bit
TIFF (same pixels, 14.4 s to 11.8 s per render and 1.2 s to 0.2 s per
tile cut). It can render measured-noise variants as crops of the tiles
with the full frame's noise passed in (`HOLIDAY_TILES=1`), but with r 8
those do not match full frames (coarse-scale windows reach past the 300
px margin), so it is off.

Strength for this setting, matching old mode's flat-area noise or the
JPEG's: about 0.6 at ISO 200, 0.75 at 640-1000, 1.0 at 6400 and up.
That still rises with ISO, less steeply than before; whether it should
be automatic is open.

## Session 14: the user's own workflow, raw neural denoise and Topaz

Five images in `C:\temp\denoise\workflow` (`GUIDE.txt` there), each as
the user's default render (their history: color balance rgb with
saturation +0.2, shadows +0.25; demosaic LMMSE with capture sharpening
radius 0.87; denoise (profiled) "Denoise chroma", wavelets Y0U0V0 at
strength 1.2 with the luma curve at 0, so chroma only), with darktable's
raw neural denoise at 25, 50 and 75 instead, and for the three high-ISO
ones Topaz DeNoise AI 3.7.1 on the default export (P1378607 Low Light,
sharpness 20, recover detail 21; P1378610 and P1378616 Severe Noise,
sharpness 100). The user's notes: at ISO 200 and 800 nothing on top of
the chroma-only preset was worth it in Topaz; a little luma grain looks
crisper. Their darktable is their own branch (`master-plus-my-fixes`).

`workflow.py` renders, from the user's own XMP with this build: their
history unchanged (a check), with denoise (profiled) off, and with it
replaced by the session 13 setting at two strengths per ISO. Tiles are
chosen as in `holiday.py`. My render of their default differs from their
export by an RMSE of 5.5%, mostly a large ring pattern over the frame
(lens correction or vignetting in their branch, not examined); Lab L in
the fine and mid bands matches within 1%, chroma does not (2.78 against
3.35 on P1378616's flat tiles), so comparisons below use L only and are
relative to my "denoise off" render.

Lab L energy relative to no denoise, flat | textured tiles:

| image | version | fine flat \| tex | mid flat \| tex | flat specks |
|---|---|---|---|---|
| P1378395 ISO 200 | their default | 1.00 \| 1.01 | 1.00 \| 1.00 | 19510 |
| | neural 50 | 0.69 \| 0.75 | 0.98 \| 0.98 | 9487 |
| | new 0.75 | 0.88 \| 0.88 | 0.94 \| 0.96 | 15142 |
| P1378550 ISO 800 | neural 50 | 0.64 \| 0.68 | 0.93 \| 0.97 | 3832 |
| | new 0.9 | 0.63 \| 0.70 | 0.83 \| 0.90 | 3528 |
| P1378607 ISO 6400 | neural 50 | 0.37 \| 0.56 | 0.43 \| 0.80 | 0 |
| | neural 75 | 0.14 \| 0.28 | 0.22 \| 0.70 | 0 |
| | Topaz | 0.27 \| 0.46 | 0.33 \| 0.79 | 0 |
| | new 0.9 | 0.36 \| 0.41 | 0.35 \| 0.69 | 0 |
| P1378610 ISO 25600 | neural 75 | 0.18 \| 0.30 | 0.28 \| 0.75 | 2592 |
| | Topaz | 0.12 \| 0.28 | 0.25 \| 0.80 | 340 |
| | new 1.0 | 0.11 \| 0.19 | 0.18 \| 0.56 | 1428 |
| P1378616 ISO 20000 | neural 75 | 0.15 \| 0.32 | 0.18 \| 0.82 | 38 |
| | Topaz | 0.11 \| 0.31 | 0.08 \| 0.93 | 0 |
| | new 1.0 | 0.14 \| 0.22 | 0.14 \| 0.65 | 244 |

(The speck count is high at low ISO because it counts fine texture and
grain.)

- **At the same flat-area noise, the neural denoise keeps more mid-band
  texture than the new mode at every ISO** (P1378550: 0.97 against 0.90
  with the same fine-band noise; P1378616: 0.82 against 0.65), and
  Topaz more still at high ISO (0.93 on P1378616, with sharpening 100).
  The new mode is last of the three denoisers on this measure in the
  user's workflow.
- Visually (2x crops of the textured tiles, not kept): Topaz is the
  cleanest and crispest, with strong edges and local contrast, and on
  P1378607 bark it draws brush-stroke-like texture that is not in the
  raw. Neural 75 is clean and soft, colors kept. **The new mode leaves
  fine grain and magenta/green colored specks in dark textured areas**,
  amplified here by the user's +0.25 shadow saturation. At ISO 200 and
  800 all versions look alike at 100%, as the user found.
- The colored specks are not the chroma guide (gone with `BNCGUIDE`
  off: unchanged), not luma-only Wiener (Wiener on all channels:
  unchanged) and not the inferred "preserve shadows" (0.5 instead:
  worse). Not found yet.

**Addendum: the render difference is the lens module.** The user's
exports came from their branch at `3ad3ebf6de` (upstream master at
`71a00aad99`, 46 commits newer than this branch's base `46908385e6`,
with `rw2-tca-pr` merged: Panasonic chromatic aberration correction from
the RW2 metadata, in `src/common/exif.cc` and `src/iop/lens.cc`), built
and rendered on Windows. Built from that commit in a separate worktree
(`/home/smuj/git/darktable-3ad3ebf6de`, its own `build/`) and run under
WSL, their default history reproduces their export to an RMSE of 0.26
and at most 11 of 65535 (P1378616, P1378395); the remainder is
presumably the platform (Windows build, possibly OpenCL, against CPU
under WSL), not examined. With the lens module off, this branch's build
and theirs render byte-identically, so the ring pattern and the chroma
difference are the metadata CA correction alone; the 46 upstream
commits change nothing here. `denoiseprofile.c` is the same in both
trees, and `bandnoise.patch` applies to theirs unchanged.

Rerun of `workflow.py` with their build and the patch (`BUILD=` the
worktree's build): their default now matches exactly in chroma as well
(P1378616 flat tiles 3.35 against 3.35, was 2.78). The L-band numbers
above change by at most 0.02 (P1378607 textured fine band), so the
conclusions stand. Flat | textured chroma, now comparable: P1378616
neural 75 1.48 | 3.91, Topaz 2.17 | 3.96, new 1.0 2.04 | 3.97;
P1378607 neural 75 0.30 | 3.73, Topaz 0.08 | 1.16, new 1.0 0.47 | 4.16.

So, against the two learned denoisers in the user's own workflow, the
measured-noise mode does not win at any ISO. It does beat old mode
(sessions 11-13) and the user's chroma-only preset at high ISO. The
user's verdict that neural restore is "nothing like Topaz" is borne out
on detail; on these numbers neural 75 is closer to Topaz than the new
mode is.

Renders and montages: `C:\temp\denoise\compare\workflow\` (tile
montages, 2x crops, the new mode at strength 1.0 for the three high-ISO
images); full renders in `/tmp/wf/run` (2.4 GB).

## Round 1 TODOs

1. **Done (session 4): what produces the dark specks.** The concave
   variance-stabilizing transform turns the low-signal noise dark-skewed,
   clipped photosites push the tail further, and soft thresholding at
   about 1.5 sigma passes the 4-5 sigma outliers. Fix directions for a
   later round, none tried: treat negative and zero input without the
   clamps (extend the transform below 0 instead), test isolated outliers
   against their neighbors before or during thresholding (soft, hard and
   garrote thresholding all pass large coefficients by design), or choose
   the exponent by signal level instead of a global `shadows`.
2. **Closed (session 5): the per-channel profile entries do not fit the
   module**, see there; the experiment is kept as `perchannel.patch`.
   Original entry: use the profile's per-channel a and b in the wavelet and
   non-local means paths instead of the green entry (`denoiseprofile.c:1532`,
   `:1688`, `:1731`). The transforms take scalar a and b today. Check
   with `bands.py` that the per-channel s0 levels move toward each other,
   then compare renders. It changes the output of every existing edit, so
   it needs a params version bump with the old behavior kept for old
   histories, unchanged results on integration tests 0013 and 0027, and
   the OpenCL path kept in sync. Whether the kernels in
   `data/kernels/denoiseprofile.cl` take scalar a and b has not been
   checked.

## Round 3 TODOs (after session 14)

State: the measured-noise mode (`bandnoise.patch`, switches in sessions
6-13; best setting: one transform exponent, inferred "preserve shadows",
r 8, Wiener luma, leave-block-out 1, despeck 2, chroma guide, shape cap,
strength about 0.6 / 0.75 / 1.0 at ISO 200 / 640-1000 / 6400+) beats old
mode and the user's chroma-only preset at high ISO but loses on texture
to darktable's raw neural denoise and to Topaz in the user's workflow
(session 14). In priority order:

1. **Upstream write-up of the low-risk findings**, for discussion before
   any code (CONTRIBUTING.md: substantial). Each stands on its own:
   - Y0U0V0 luma about 5x and chroma about 0.25x the noise the model
     assumes: cross-channel correlation after demosaic, and the Y0 row
     multiplying by sum(1/wb) (`denoiseprofile.c:1311`, session 5);
   - the specks: dark-skewed noise after the transform, clipped
     photosites, soft thresholding (session 4), and despeck plus Wiener
     as a fix (session 8);
   - capture sharpening in demosaic raises the noise the module sees
     and old mode does not adapt (session 10);
   - per-channel profile entries do not fit white-balanced data
     (session 5);
   - the rock tint: removing chroma detail while keeping luma detail
     tints neutral texture, made worse by the white-balance-adaptive
     transform (session 10).
   Include the measurements, the scripts that reproduce them, and say
   plainly that the full new mode does not beat learned denoisers.
2. **The colored specks** in dark textured areas at ISO 6400+ in the
   user's workflow (session 14). Not the chroma guide, luma-only Wiener
   or "preserve shadows". Next: dump U0/V0 detail bands on a P1378607
   bark crop, check whether they are chroma outliers the despeck pass
   misses (it tests each channel against its own neighbors), and
   whether they appear without the user's color balance rgb.
3. **Decide whether to continue the wavelet mode at all.** If yes, the
   open items before it could be a real mode: a noise-dependent
   strength (the matching strength still rises with ISO), the edge halo
   (session 8), the steep strength response, the noise shape from the
   profile instead of a fixed table (session 12), the OpenCL path, a
   params version with old histories unchanged, other cameras.
4. **Why the neural denoise loses to Topaz on detail** (session 14).
   Model and training questions more than darktable ones; possibly
   tile size, input normalization or the strength blend in
   `src/common/ai/restore_raw_bayer.c`. Read before measuring.
5. **Profiling convention** (round 2 candidate 3): profiles are measured
   without white balance and with the finest Haar diagonal coefficient
   (sessions 3, 5), both unlike what the module sees.
6. Smaller loose ends:
   - (done, session 14 addendum) my render of the user's default
     history differed from their export: the RW2 CA correction from
     `rw2-tca-pr` in their build. Compare future workflow renders with
     their build (`/home/smuj/git/darktable-3ad3ebf6de/build`);
   - the default "as shot" white balance comes with late correction,
     so without color calibration the output is camera reference, not
     as shot (session 9 note);
   - `holiday.py`'s tile renders (`HOLIDAY_TILES=1`) do not match full
     frames at r 8; widen the margin or drop the option.

Scratch data that later steps may reuse, moved off WSL to
`C:\temp\denoise\scratch\` as tar archives that unpack to the paths
the scripts use (`cd /tmp && tar xf /c/temp/denoise/scratch/hol.tar`):
`hol.tar` (`/tmp/hol`: run/ with the 79 holiday images' tiles of every
variant, metrics and XMPs, plus the shape logs and helper scripts,
2.7 GB), `wf.tar` and `wf_tif.tar` (`/tmp/wf/run`: session 14 tiles,
metrics, XMPs, and the full renders from this branch's build, 0.1 and
2.4 GB), `wf2.tar` (`/tmp/wf2/run`: the same rendered with the user's
build, the ones to use, 2.5 GB), `dn11.tar`
(`/tmp/dn11` and `/tmp/dn10`: session 9-10 renders, 1.1 GB).

## Round 2 candidates

1. **Y0U0V0 noise normalization.** Luma 5x, chroma 0.25x the model
   (session 5). **Tried in sessions 6-8** by measuring the noise per
   band; normalization works, and local Wiener (luma) / BayesShrink
   (chroma) with a despeck pass gives the best result seen (session 8).
   Open before it could become a real mode: the edge halo, strength
   entering once and its steep response, the OpenCL path (the local
   variance needs a box filter there too), other files and ISOs, and a
   params version with the old behavior kept for old histories.
2. **The specks** (session 4 has the fix directions). Removed in the
   local mode by session 8; the clipping and transform-exponent directions
   were not needed and not tried. Next in that line: the grain halo along
   edges.
3. **Profiling convention.** Profiles are measured without white balance
   (`tools/noise/profiling-shot.xmp`) and with the finest Haar diagonal
   coefficient (session 3); both differ from what the module sees.

## Later

1. Is the low absolute level specific to high ISO? Run `bands.py` on a flat
   area of an ISO 200 G9 file and on another camera.
2. Does the profiling-tool convention (Haar HH after demosaic) explain the
   gap quantitatively? Simulating white CFA noise through RCD and PPG and
   measuring both HH and per-band sigma would answer it.
3. How far is darktable from the JPEG once color and sharpening match? Build
   a proper history for P1378616 (its own WB and color calibration, some
   sharpening or diffuse or sharpen) before judging detail.

## What is not claimed here

- That the G9 or its JPEG engine does anything in particular; none of its
  processing was inspected.
- That the findings hold beyond this one ISO 20000 file and one patch.
- Anything about the OpenCL path: every render here ran on the CPU. The
  machine is WSL2 (kernel 6.18.58.1-microsoft-standard-WSL2): `/dev/dxg` is
  there, but the only OpenCL runtime installed is the native AMD APP one
  (`/etc/OpenCL/vendors/amdocl64_60402_120.icd`), which finds 0 devices
  (`clinfo -l`, `darktable-cltest`). OpenCL under WSL needs a runtime that
  goes through `/dev/dxg`; none was tried.
