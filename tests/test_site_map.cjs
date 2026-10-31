/* Slippy map maths: roundtrips, dateline, limits and site picker wiring. */
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");
const code = fs.readFileSync("static/site-map.js", "utf8");
const app = fs.readFileSync("static/v2.js", "utf8");
const html = fs.readFileSync("templates/v2.html", "utf8");
const context = vm.createContext({ window: {} });
vm.runInContext(code, context);
const map = context.window.HFTASitePicker;
assert(map && typeof map.create === "function");
for (const [lat, lon, zoom] of [[41.43889, -73.40383, 18], [43.6724, -72.0136, 15],
  [-33.9, 151.2, 7], [65.5, -147, 10], [0, 179.9, 12]]) {
  const w = map.world(lat, lon, zoom);
  const p = map.position(w.x, w.y, zoom);
  assert(Math.abs(p.lat - lat) < 1e-6, `Latitude changed for ${lat}, ${lon}`);
  assert(Math.abs(p.lon - lon) < 1e-6, `Longitude changed for ${lat}, ${lon}`);
}
assert.equal(map.normLon(190), -170);
assert.equal(map.normLon(-190), 170);
assert.equal(map.position(0, 0, 7).lat > 85, true);
assert(code.includes("https://tile.openstreetmap.org/"), "OSM HTTPS tile source missing");
assert(code.includes("strict-origin-when-cross-origin"), "OSM Referer requirement not supported");
assert(code.includes("OpenStreetMap contributors"), "Visible OSM attribution missing");
assert(code.includes("replaceChildren(fragment)"), "Tile cache should retain existing viewport tiles");
assert(app.includes('data-act="map"'), "Sites page map button missing");
assert(app.includes('data-act=map'), "Map button listener missing");
assert(app.includes('HFTASitePicker.create'), "Map modal not wired");
assert(app.includes('/position`'), "Server-side coordinate update missing");
assert(html.includes("site-map.js"), "First-party map script not bundled");
console.log("PASS: accurate map projection, attribution, privacy and Sites dialog wiring");
