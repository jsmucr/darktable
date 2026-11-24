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
  **retracted**. New: dark blue-green speckle in the rock texture.

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
- `quick.sh` renders only the three `tradeoff.py` regions of P1378616 as
  a crop set (session 8), in 4-10 s per variant; `crop_xmp.py` writes the
  cropped histories, and `tradeoff.py` takes a crop set's prefix in place
  of a render. `session8.sh` re-runs session 8 with it in about 5 minutes.
- `perchannel.patch`: the session 5 experiment, switched on with
  `DT_DN_PERCHANNEL=1`; bit-identical output when off.
- `bandnoise.sh` re-runs sessions 6 and 7 in about 20 minutes: it renders four
  references with the clean module, applies `bandnoise.patch`, checks they
  are unchanged with the switches off, renders the strength sweeps and
  variants at 16 bit, prints `tradeoff.py` for all of them, the per-scale
  estimates and thresholds, and the wall's own band noise, and restores the
  source on exit. Leaves about 3.3 GB of renders in its work directory.
- `bandnoise.patch`: the session 6-8 experiments (`DT_DN_BANDNOISE=1`
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
data denoise (profiled) sees does not change. New mode: Wiener luma, r 8,
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
  the JPEG does not have. Most likely chroma noise surviving in texture,
  where the local window takes the luma texture's variance as chroma
  signal too. Not measured yet.

The renders, the side-by-side and the 100% crops are in
`/c/temp/denoise/compare/` on this machine, with the history used.

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
