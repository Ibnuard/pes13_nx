# FEXTendo v3.2 assets

## Settings and Credits

Created with the built-in OpenAI image generation tool for this project on
2026-09-29. These are the final flat variants requested by the user. The earlier
ornate drafts were rejected and are not included or used. No Autorun image was
used as an input. Both files are the unmodified generated PNGs; the asset builder
resamples them with Lanczos to 256×256 RGBA. The native renderer supplies rounded
corners, focus animation and perimeter glow.

- `settings-flat.png`: white sliders and cyan knobs on navy.
- `credits-flat.png`: two overlapping contributor cards on navy.

Settings prompt (verbatim):

> Use case: stylized-concept. Create a flat minimalist SETTINGS icon tile for a modern console launcher, square 1024x1024. Full bleed nearly black navy background with a very subtle deep blue gradient. Center one bold clean graphic of three horizontal adjustment sliders, white tracks with generously sized round cyan knobs staggered left/right/middle. Perfectly smooth rounded shapes and balanced spacing. Icon centered, occupies 48% of canvas width. Contemporary flat 2D console home screen aesthetic, extremely restrained and instantly readable at 200 pixels. No text, no letters, no outer tile outline, no glow baked in, no 3D, no shadows, no bevels, no glass objects, no gears, no texture or tiny detail. Keep generous navy negative space. Application supplies rounded corners and animated focus glow.

Credits prompt (verbatim):

> Use case: stylized-concept. Create a flat minimalist CREDITS / PROJECT TEAM icon tile for a modern console launcher, square 1024x1024. Full bleed nearly black navy background with a very subtle deep blue gradient. Center one bold clean graphic showing two overlapping contributor profile cards, the front card white with a simple navy head-and-shoulders silhouette and two short navy identity lines, the rear card cyan offset slightly up-left. Smooth rounded shapes, no outline strokes, extremely simple graphic construction. Icon centered, occupies 48% of canvas width. Contemporary flat 2D console home screen aesthetic, restrained and readable at 200 pixels. No text, no letters, no outer tile outline, no baked glow, no 3D, no shadows, no bevels, no glass, no metallic effects, no texture or tiny detail. Keep generous navy negative space. Application supplies rounded corners and animated focus glow.

## Original audio

`tools/build-fextendo-audio.py` synthesizes a 16-second ambient loop from four
open chord voicings, decaying sine partials and wrapped delay taps, with a short
seam fade. There are no recordings, downloaded tracks or samples in this loop.
The user-supplied `xtremefreddy-game-music-loop-1-143979.mp3` is not used or packaged.

`src/runtime/fextendo_sfx.h` synthesizes the four navigation/confirm/back/error
cues with mallet-like partials and short amplitude envelopes. These replace the
previous original frequency-sweep cues; neither set was copied from Autorun.
Synthesis code retains the project source license. Music is loaded once into
launcher memory and mixed as PCM; no MP3 decoder, streaming or game-time audio
worker is introduced. BGM and SFX have independent persisted switches.

Rebuild: `python3 tools/build-fextendo-assets.py OUTPUT_RUNTIME_ROOT` (Pillow and
CairoSVG required). The output manifest hashes both PNGs, the audio generator
and every generated binary. `tools/build-fextendo-audio.py OUTPUT --preview
preview.wav` also produces an auditionable WAV from the identical PCM.
