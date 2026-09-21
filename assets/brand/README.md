# Prudence logo

The approved mark is A1 from the final proportion study (22.5 degrees; the founder moved from A3 on 2026-09-20 because 25 degrees looked too slanted).

- `logo.svg`: dark mark (`#111111`) for light backgrounds.
- `logo-white.svg`: white mark (`#FFFFFF`) for dark backgrounds.
- `logo-glyph-template.svg`: the menu-bar template glyph, derived from the mark.

All three are transparent SVGs carrying a `viewBox` and no fixed pixel size, so a
surface sizes them itself. The fill sits on each `<path>` rather than on a wrapper,
which is what a template renderer expects, and each file names itself in a `<title>`.
They contain the exact vector paths and can be used directly or exported at the
required resolution. Scale uniformly and preserve the supplied spacing and three
separate pieces. The SVGs retain the approved study framing; the visible mark is wider
than tall, and its own bounding box inside the 512 × 512 frame is
`58.094 116.072 397.052 279.857`.

## Uses

| Use | File | Minimum size | Note |
|---|---|---|---|
| App icon master | `logo.svg` | 1024 px | The mark centred on the macOS icon squircle. The 1024 px master and the derived icon set are batch 1 work. |
| Menu-bar template glyph | `logo-glyph-template.svg` | **16 px** | 16 × 16 pt with 1 px optical padding. Rendered as a template image: the system takes the alpha and supplies the colour. |
| Popover and window header | `logo.svg` / `logo-white.svg` | 16 px | About 18 px tall beside the product name; pick the file by the background, not by the appearance setting. |
| README and documentation badge | `logo.svg` / `logo-white.svg` | 24 px | Never below 24 px in prose, where no optical padding is applied. |

The glyph is the one derived file. Its two bowl pieces are merged into one, because at
16 pt the mark's two 20-unit gaps both fall to about 0.63 pt and read as noise rather
than as separation; merging leaves a single gap of about 0.7 pt, which holds. The leg,
the outline and the proportions are untouched. Nothing else derives from the mark by
hand: scale it uniformly instead.

## Geometry

- Height multiplier: `224 * (1 + 1/3) / 360 = 0.8296296296296295`.
- Side-edge inclination: 22.5 degrees from vertical; horizontal caps and cuts.
- Head height to lower extension: 3:1.
- Stem thickness perpendicular to its sides: `112 * cos(20 degrees)` units.
- Stem-to-head gap: 20 units perpendicular to the parallel sides.
- Horizontal split: 20 units; rounded stem corner radius: 52 units.

The height multiplier refers to a 360-unit master, not the logo's aspect ratio.
The head curves are fixed; the stem and lower-left edge are constructed for the
selected inclination. Display placement uses translation and uniform scaling.
A1 (like the whole A row) is based on 3:1, rather than the golden-derived ratio used in another study row.

## License

See the repository [Apache-2.0 license](../../LICENSE). Section 6 addresses
trademarks; this document does not add a separate trademark license or imply
that the Prudence name or logo is a registered trademark.
