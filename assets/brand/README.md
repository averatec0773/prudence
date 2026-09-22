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
| Menu-bar template glyph | `logo-glyph-template.svg` | **20 × 18 pt** (fixed) | Ink 18 × 12.49 pt with 1 pt of clear space each side. Rendered as a template image: the system takes the alpha and supplies the colour. |
| Popover and window header | `logo.svg` / `logo-white.svg` | 16 px | About 18 px tall beside the product name; pick the file by the background, not by the appearance setting. |
| README and documentation badge | `logo.svg` / `logo-white.svg` | 24 px | Never below 24 px in prose, where no optical padding is applied. |

The glyph is the one derived file, and it is derived for one size: the macOS menu bar.
Three things change there, and nothing else does.

**It is wider than tall.** The mark is 1.42 times wider than it is tall, so fitting it
into a square spends most of the square on empty space and leaves the ink about 14 pt
wide, smaller than the status items either side of it. The glyph's canvas is 20 × 18 pt
instead, carrying ink 18 × 12.49 pt with 1 pt of clear space each side. The 18 pt height
is not a preference: `tray-icon` sets the status item's image to a fixed 18 pt height and
scales the width by the aspect ratio, so a canvas of any other height would be rescaled
on the way to the screen and every measurement here would be wrong.

**Both gaps open from 20 to 26 units, at this size only.** At the mark's own proportions
a 20-unit gap is 0.84 pt, under two device pixels on a Retina menu bar, and it closes up.
26 units is 1.0876 pt, a little over two device pixels, which holds. The horizontal split
is a band 26 units high centred on y = 112 in the mark's coordinates; the stem-to-head gap
is opened by moving the head right by `(26 - 20) / cos(22.5 degrees)` units, which is the
distance that widens a 22.5 degree slot by 6 units measured perpendicular to its sides.

**Nothing is merged.** The bowl is two separate paths again. An earlier glyph bridged them
with a fourth rectangle because at 16 pt neither gap survived; at this size both do, so
the bridge is gone. The leg, the outline and the proportions are untouched, and the mark
itself (`logo.svg`, `logo-white.svg`) does not change.

The split is placed on the 2x device-pixel grid as closely as the geometry allows, which
is not exactly. The band is 1.0876 pt and a device pixel at 2x is 0.5 pt, so 0.0876 pt is
left over whatever the placement, and the best any placement can do is halve it. Each edge
is therefore 0.0438 pt (0.088 device pixels) off the grid, and the split renders as two
fully clear pixel rows with a 6 percent nick on each side. The ink's vertical position in
the canvas is the one degree of freedom available and the split takes it, which leaves the
head's cap and the stem's foot 0.37 and 0.38 device pixels off. That is the trade, and it
is deliberate: the split is the finest feature on the glyph, so blur costs it the most.

Nothing else derives from the mark by hand: scale it uniformly instead.

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
