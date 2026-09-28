# Covenant brand assets

Interlocking violet ribbons forming a triangular knot. SVG files contain vector paths only; lettering is outlined and requires no fonts. All logos have transparent backgrounds.

Palette: `#14213D`, `#3E254E`, `#503065`, `#7B56AD`, `#9675D1`. Dark-background ink: `#E8EFFA`.

## Files

- `svg/`: symbol, wordmark, horizontal and stacked logos. Each has standard, `-dark`, `-mono-black` and `-mono-white` variants.
- `png/`: transparent wordmarks and logos at 1200 px wide; icons at 128, 256, 512 and 1024 px, plus dark and monochrome icons at 512 px.
- `favicon/`: adaptive SVG, multi-resolution ICO (16/32/48), PNG favicons, Apple touch icon (180), Android icons (192/512) and web manifest. Apple touch icon has a white background.

Use the standard palette on light backgrounds and `-dark` on dark backgrounds. Keep proportions and allow clear space around the logo. The monochrome variants are intended for single-colour printing or constrained interfaces.

## Rebuild raster exports

From the repository root, with Python 3 and the optional brand tooling installed:

```sh
python -m pip install cairosvg Pillow
python scripts/build_brand_assets.py
```

The SVG files are the editable vector masters. No image tracing or external fonts are needed to regenerate exports.

## Website integration

Copy the contents of `favicon/` to your public asset directory, preserving relative paths. Adapt the URL prefix below to your deployment:

```html
<link rel="icon" href="/favicon/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="apple-touch-icon" href="/favicon/apple-touch-icon.png">
<link rel="manifest" href="/favicon/site.webmanifest">
```

These files supply the brand assets; they do not change application routing or install favicon links automatically.
