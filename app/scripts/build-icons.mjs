// Renders the app icon and the Microsoft Store art from one vector source, so
// the Store logos cannot drift from the icon on the exe.
//
//   pnpm icons
//
// The mark: one line, the mix, fanning out into four, the stems, in the
// colours the UI gives separation, ensemble, subtract and post-process. It
// is drawn in a 1024-unit box and scaled for each output.
//
// Out:  assets/icon.svg                      the icon, as vector
//       assets/icon.png                      1024 × 1024, electron-builder makes the .ico/.icns
//       ../docs/store/box-art-2160.png       1:1 box art, required for MSI/EXE listings
//       ../docs/store/poster-art-1440x2160.png  2:3 poster art, recommended
//       ../docs/store/app-tile-300.png       1:1 tile, recommended
//
// Two of Microsoft's rules are kept by construction: the bottom third of the
// box and poster art holds nothing but background, since the Store may
// overlay text there, and there is no text on the art at all.

import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const here = path.dirname(fileURLToPath(import.meta.url));
const appDir = path.resolve(here, "..");
const storeDir = path.resolve(appDir, "..", "docs", "store");

// From app/src/renderer: --panel/--bg for the tile, --text for the mix,
// --op-separate, --op-ensemble, --op-subtract, --op-postprocess for the stems.
const TILE_TOP = "#2a3042";
const TILE_BOTTOM = "#101320";
const MIX = "#e4e7ee";
const STEMS = ["#4aa3ff", "#f5a524", "#c084fc", "#3fb97c"];

const BOX = 1024;
const STEM_Y = [272, 432, 592, 752];
const SPLIT_X = 416;
const STEM_END_X = 848;

// The mark alone, drawn in the 1024 box.
function mark() {
  const stems = STEM_Y.map(
    (y, i) =>
      // The same S-curve scaled vertically for each stem, so no two stems cross.
      `<path d="M${SPLIT_X} 512 C 520 512, 512 ${y}, 616 ${y} L ${STEM_END_X} ${y}" ` +
      `stroke="${STEMS[i]}" stroke-width="72" stroke-linecap="round" fill="none"/>`,
  ).join("\n    ");
  // The mix is drawn last and wider, so its round cap covers the four
  // starts and the split reads as one clean fork.
  const mix = `<path d="M176 512 L ${SPLIT_X} 512" stroke="${MIX}" stroke-width="88" stroke-linecap="round" fill="none"/>`;
  return `${stems}\n    ${mix}`;
}

// A whole image: tile background, then the mark scaled and centred on (cx, cy).
function svg({ width, height, radius, scale, cx, cy }) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${TILE_TOP}"/>
      <stop offset="1" stop-color="${TILE_BOTTOM}"/>
    </linearGradient>
    <radialGradient id="glow" cx="${cx / width}" cy="${cy / height}" r="0.55">
      <stop offset="0" stop-color="#4aa3ff" stop-opacity="0.16"/>
      <stop offset="1" stop-color="#4aa3ff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="${width}" height="${height}" rx="${radius}" fill="url(#tile)"/>
  <rect width="${width}" height="${height}" rx="${radius}" fill="url(#glow)"/>
  <g transform="translate(${cx - (BOX / 2) * scale} ${cy - (BOX / 2) * scale}) scale(${scale})">
    ${mark()}
  </g>
</svg>
`;
}

const outputs = [
  // The icon: a rounded tile with transparent corners.
  { file: path.join(appDir, "assets", "icon.png"), width: 1024, height: 1024, radius: 232, scale: 1, cx: 512, cy: 512, svg: path.join(appDir, "assets", "icon.svg") },
  // Store art is full-bleed; the Store rounds its own tiles.
  { file: path.join(storeDir, "box-art-2160.png"), width: 2160, height: 2160, radius: 0, scale: 2160 / BOX, cx: 1080, cy: 1080 },
  { file: path.join(storeDir, "app-tile-300.png"), width: 300, height: 300, radius: 0, scale: 300 / BOX, cx: 150, cy: 150 },
  // Poster: the mark sits in the upper two thirds; the bottom third (y > 1440) is background only.
  { file: path.join(storeDir, "poster-art-1440x2160.png"), width: 1440, height: 2160, radius: 0, scale: 1.1, cx: 720, cy: 760 },
];

for (const out of outputs) {
  const source = svg(out);
  mkdirSync(path.dirname(out.file), { recursive: true });
  if (out.svg) writeFileSync(out.svg, source);
  const png = new Resvg(source, { fitTo: { mode: "width", value: out.width } }).render().asPng();
  writeFileSync(out.file, png);
  console.log(`${path.relative(path.resolve(appDir, ".."), out.file)}  ${out.width}x${out.height}  ${(png.length / 1024).toFixed(0)} KB`);
}
