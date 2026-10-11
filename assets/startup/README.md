The embedded startup GUI uses the same font atlas and wordmark as the approved
original launcher. They remain available when the SD runtime needs repair.

- `font.dat`: Inter atlas (`font.bin` in the runtime), SHA256
  `d11b74e220b5b2ffdb90fa15155022879732f736426d36e50e21c33dfef1cae2`.
  License: `assets/fonts/OFL.txt`.
- `wordmark.rgba`: 600 x 128 RGBA, SHA256
  `13e55184bc6bef84a06abf6beec4768f19d911274a9e5ff7643a1bf145d13074`.
  Source: `assets/fextendo-v2/wordmark.png`.

`tools/fextendo_startup_assets.py` embeds these immutable bytes at build time.
No console or SD artwork is required to show the splash or startup modal.
