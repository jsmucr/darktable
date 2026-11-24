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
- **The absolute level the module works with is too low:** measured band
  sigmas are 1.4-1.75x the model in green and 1.8-2.5x in red and blue. Part
  of it is in the code: the wavelet and non-local means paths use only the
  green profile entry for all channels (`denoiseprofile.c:1532`, `:1688`,
  `:1731`), although the profile carries R and B values (session 3).
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

Builds: `build-dn/` is a separate tree configured from this branch
(`cmake -S . -B build-dn -DCMAKE_BUILD_TYPE=RelWithDebInfo`). Do not
rebuild single modules of the user's `build/` from this branch: it is
built from `rw2-tca-pr`, whose `src/common/image.h` differs, so a module
built here would not match its `dt_image_t`.

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
  sqrt(a_R/a_G) = 1.27, sqrt(a_B/a_G) = 1.21.
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
2. **Use the profile's per-channel a and b** in the wavelet and non-local
   means paths instead of the green entry (`denoiseprofile.c:1532`,
   `:1688`, `:1731`). The transforms take scalar a and b today. Check
   with `bands.py` that the per-channel s0 levels move toward each other,
   then compare renders. It changes the output of every existing edit, so
   it needs a params version bump with the old behavior kept for old
   histories, unchanged results on integration tests 0013 and 0027, and
   the OpenCL path kept in sync. Whether the kernels in
   `data/kernels/denoiseprofile.cl` take scalar a and b has not been
   checked.

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
- Anything about the OpenCL path: every render here ran on the CPU.
