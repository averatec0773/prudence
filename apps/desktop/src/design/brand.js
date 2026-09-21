/* The brand mark and the menu-bar glyph.
 *
 * Carried as markup rather than as file references, so a page has them without a fetch.
 * The paths are generated from `assets/brand` by
 * `docs/design/mockups/build_standalone.py`; the fill is `currentColor`, which is how a
 * surface picks the dark or the light artwork by setting `--brand-ink`.
 */

var MARK_VIEWBOX = "58.094 116.072 397.052 279.857";
var MARK_INNER = "<g transform=\"translate(280.75668274 116.07172163) scale(0.93701972)\"><path fill=\"currentColor\" d=\"M -79.17169873 0 H 0 L -110.41533744 266.56620515 A 52 52 0 0 1 -158.45707313 298.66666667 H -237.62877186 L -127.21343442 32.10046152 A 52 52 0 0 1 -79.17169873 0 Z\"/><path fill=\"currentColor\" d=\"M 21.64784401 0 H 106.36428856 C 124.89360649 0 141.46021489 4.59718781 154.57948029 13.37958178 C 167.69874569 22.16197575 176.96076268 34.85517401 181.53550619 50.32166269 C 186.11024969 65.78815138 185.85478396 83.54468714 180.7920028 102 H 107.23932466 C 59.96845518 102 21.64784401 56.33304448 21.64784401 0 Z\"/><path fill=\"currentColor\" d=\"M -28.8862106 122 H 173.51259811 C 165.14101018 140.45531286 152.47077495 158.21184862 136.63734843 173.67833731 C 120.8039219 189.14482599 102.30201223 201.83802425 82.78968685 210.62041822 C 63.27736146 219.40281219 43.36427402 224 24.83495608 224 H -71.13599397 Z\"/></g>";
var GLYPH_VIEWBOX = "0 0 16 16";
var GLYPH_INNER = "<g fill=\"currentColor\" transform=\"translate(-1.054796 -1.054794) scale(0.03537029)\"><g transform=\"translate(280.75668274 116.07172163) scale(0.93701972)\"><path d=\"M -79.17169873 0 H 0 L -110.41533744 266.56620515 A 52 52 0 0 1 -158.45707313 298.66666667 H -237.62877186 L -127.21343442 32.10046152 A 52 52 0 0 1 -79.17169873 0 Z\"/><path d=\"M 21.64784401 0 H 106.36428856 C 124.89360649 0 141.46021489 4.59718781 154.57948029 13.37958178 C 167.69874569 22.16197575 176.96076268 34.85517401 181.53550619 50.32166269 C 186.11024969 65.78815138 185.85478396 83.54468714 180.7920028 102 H 107.23932466 C 59.96845518 102 21.64784401 56.33304448 21.64784401 0 Z\"/><path d=\"M 107.23932466 102 H 173.51259811 V 122 H 107.23932466 Z\"/><path d=\"M -28.8862106 122 H 173.51259811 C 165.14101018 140.45531286 152.47077495 158.21184862 136.63734843 173.67833731 C 120.8039219 189.14482599 102.30201223 201.83802425 82.78968685 210.62041822 C 63.27736146 219.40281219 43.36427402 224 24.83495608 224 H -71.13599397 Z\"/></g></g>";
var NS = "http://www.w3.org/2000/svg";
var ASPECT = 1.418769;

/**
 * @param {string} viewBox
 * @param {string} inner
 * @param {number} height
 * @param {string} [label]
 * @returns {SVGSVGElement}
 */
function svg(viewBox, inner, height, label) {
    const node = /** @type {SVGSVGElement} */ (document.createElementNS(NS, "svg"));
    node.setAttribute("viewBox", viewBox);
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", label || "Prudence");
    node.setAttribute("height", String(height));
    node.style.height = height + "px";
    node.style.width = "auto";
    node.style.display = "block";
    node.innerHTML = inner;
    return node;
}

/** The mark's own width over its own height, cropped to its bounding box. */
export { ASPECT };

/**
 * The mark, fitted into a square box of `size` points.
 *
 * The design gives the mark an 18 pt box, not an 18 pt height: the artwork is 1.42 times
 * wider than it is tall, so asking for a height of 18 draws it 42 per cent too large.
 * This takes the box and derives the height, which is what `.scaledToFit()` in a square
 * frame does on the other side.
 *
 * @param {number} [size] the side of the square box, in CSS pixels
 */
export function mark(size) {
return svg(MARK_VIEWBOX, MARK_INNER, (size || 18) / ASPECT);
}

/** The menu-bar template glyph, square, 16 by 16 with 1 px optical padding. */
export function glyph(size) {
return svg(GLYPH_VIEWBOX, GLYPH_INNER, size || 16);
}
