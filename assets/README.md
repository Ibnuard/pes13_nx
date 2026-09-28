# PES13-NX icon

## FEXTendo v2

The v2 launcher uses generated `fextendo-v2/stadium.png`, `gamepad-flat.png`
and `wordmark.png`, plus the user-supplied `logo.png` and `icon.png`.
Prompts and provenance are in `fextendo-v2/GENERATION.md`. Color scrims,
rounded corners, glossy animation and footer blur are rendered in C.

Controller sprites come from the user-supplied `Solid Duo/Dark theme/`
set. Rights remain with their creators, independently of code/font licenses.
V2 uses Inter under SIL OFL 1.1; font and license are in `fonts/Inter/`.
The earlier v1 assets and Barlow attribution are retained below.

The Fextendo launcher uses the user-supplied `PES13WP.jpg` wallpaper,
`logo.png`, and `icon.png` (the same image on both menu tiles). These are
separate from the older generated NRO icon below. Their original files are
preserved; `tools/build-fextendo-assets.py` fits them to the native UI buffers.

The launcher uses Barlow Regular and SemiBold from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/barlow), copyright
2017 The Barlow Project Authors, under SIL OFL 1.1. The font files and complete
license are in `fonts/`; the build generates a glyph atlas for the C renderer.

## Existing NRO icon

`icon-source.png` was created with the built-in image generation tool.
`icon.jpg` is the 256x256, 24-bit baseline JPEG used by elf2nro (quality 92).
The resize and JPEG encoding used Windows System.Drawing; the generated design
was not redrawn. The icon is embedded inside the NRO's ASET section.

Prompt:

> Create one square application icon for a Nintendo Switch homebrew project
> named PES13-NX, a football game port. This is a production icon to be legible
> at 256x256 pixels. Design: a bold premium sports emblem, dark midnight navy
> background, rich red angular stripe and subtle green football pitch line
> accents, one crisp white and black football near the upper center, very
> large sharply readable bold condensed white text 'PES13' across the middle
> and a smaller but still prominent red badge with white letters 'NX'
> underneath. Symmetrical balanced square composition, generous safe margins,
> flat clean graphic shapes with restrained depth, high contrast, polished
> game-library icon, no tiny lettering, no additional words, no real player
> photographs, no console logos, no external border, fully opaque background
> filling the square. Text exactly PES13 and NX. Generate a single complete
> icon with no mockup, no variants.
