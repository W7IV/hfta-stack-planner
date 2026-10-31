/* Saved-tower-to-Stack-Designer regression. Run: node tests/test_designer_load_tower.cjs */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync("static/v2.js", "utf8");
const start = source.indexOf("function designerSettingsFromTower(");
const end = source.indexOf("function compForm()", start);
assert(start >= 0 && end > start, "Import function missing");
const ctx = vm.createContext({
  elOf: a => Object.fromEntries(Object.entries(a.el || {}).filter(([, n]) => n)),
  describe: a => Object.entries(a.el).map(([band, n]) => `${band} m ${n}-el`).join("/"),
});
vm.runInContext(source.slice(start, end), ctx);
const convert = vm.runInContext("designerSettingsFromTower", ctx);
const project = {
  sites: [{ id: "siteA" }, { id: "siteB" }],
  targets: [{ id: "Europe" }, { id: "USA" }],
};
const tower = {
  id: "tower1", name: "Tower 1", site: "siteB", height_ft: 145, switching: "full",
  targets: ["Europe"], guys: { levels: [{ h: 110, r: 95, wire: "1/4 EHS steel" }] },
  antennas: [
    { h: 55, el: { "20": 4, "15": 4, "10": 4 }, turning_radius: 18, droop: 1.2 },
    { h: 95, el: { "20": 4, "15": 4, "10": 4 }, turning_radius: 18, droop: 1.2 },
    { h: 130, el: { "40": 3 }, turning_radius: 27, droop: 2.0 }
  ]
};
const original = JSON.stringify(tower);
const out = convert(tower, project, { max_height: 160, groups: [{ name: "wrong defaults" }], weights: { Europe: 2 } });
assert.equal(JSON.stringify(tower), original, "Saved tower was mutated");
assert.equal(out.source_tower_id, "tower1");
assert.equal(out.max_height, 145, "Designer incorrectly used default 160 ft");
assert.equal(out.site, "siteB");
assert.equal(out.switching, "full");
assert.equal(out.guys_from_tower, "tower1");
assert.equal(out.groups.length, 2, "Wrong antenna groups were imported");
assert.equal(out.groups[0].count, 2);
assert.deepEqual({ ...out.groups[0].el }, { "20": 4, "15": 4, "10": 4 });
assert.deepEqual([...out.groups[0].source_heights_ft], [55, 95]);
assert.equal(out.groups[0].turning_radius, 18);
assert.equal(out.groups[0].droop, 1.2);
assert.equal(out.groups[0].min_spacing, 30);
assert.equal(out.groups[0].hi, 145);
assert.equal(out.groups[1].count, 1);
assert.deepEqual({ ...out.groups[1].el }, { "40": 3 });
assert.deepEqual([...out.groups[1].source_heights_ft], [130]);
assert.equal(out.groups[1].turning_radius, 27);
assert.equal(out.weights.Europe, 2);
assert.equal(out.weights.USA, 0);
assert.equal(out.range_blanked, true);

const one = convert({
  id: "one", name: "Single tower", site: null, height_ft: 80,
  antennas: [{ h: 100, el: { "20": 4, "6": 5 } }]
}, project);
assert.equal(one.max_height, 100, "Cannot set maximum below antenna height");
assert.equal(one.groups.length, 1);
assert.deepEqual({ ...one.groups[0].el }, { "20": 4 });
assert(one.import_note.includes("6 m"));
assert.equal(one.groups[0].count, 1);
assert.equal(one.guys_from_tower, "");
assert.equal(one.weights.USA, 1);

const invalid = [
  { id: "noant", antennas: [] },
  { id: "only6", antennas: [{ h: 90, el: { "6": 4 } }] },
  { id: "mixed", antennas: [{ h: 70, el: { "20": 3 } }, { h: 110, el: { "20": 4 } }] },
  { id: "badheight", antennas: [{ h: -10, el: { "20": 4 } }] },
];
for (const v of invalid) assert.throws(() => convert(v, project), { name: "Error" }, v.id);

// This user-facing distinction is important: selecting a guy constraint
// must not pretend to import antenna and tower height.
assert(source.includes('id="cmLoadTower"'), "Explicit import action absent");
assert(source.includes("Guy constraints only (from tower)"), "Guy-only selector ambiguous");
assert(source.includes("designerSettingsFromTower(selected, p, f)"), "Import action not wired");
console.log("PASS: physical tower heights, antenna models/counts, guys, site, target scope, and non-mutating import");
