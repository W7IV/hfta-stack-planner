/* The comparison view must show real 0.25-degree OpenHFTA elevation curves.
   Run with: node tests/test_pattern_plot.cjs */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync("static/v2.js", "utf8");
const start = source.indexOf("async function showElevationPatterns(");
const end = source.indexOf('const WORLD = "__world__";', start);
assert(start >= 0 && end > start, "OpenHFTA pattern renderer not found");
const plot = { hidden: false }, note = { textContent: "" }, controls = { innerHTML: "", textContent: "" };
const elements = { "#patternControls": controls, "#cmpPlot": plot, "#patternNote": note,
  "#patternBand": {}, "#patternHeading": {} };
let drawn = null;
const gain = Array.from({ length: 140 }, (_, i) => 7 + 10 * Math.sin(i / 8));
const angles = Array.from({ length: 140 }, (_, i) => 0.25 * (i + 1));
const response = { cell: { best: 0, options: [{ az: [{ az: 48, run: "r0", fom: 11.0 }, { az: 56, run: "r1", fom: 10.5 }] }] },
  angles, patterns: { r0: gain, r1: gain.map(v => v - 4) }, aoa: { 5: 0.15, 12: 0.4 } };
const context = vm.createContext({
  CMP: { target: "EU", patternBand: null, patternOffset: 0, plotSeq: 0 },
  META: { bands: ["40", "20"] }, PAL: ["#123456"],
  P: () => ({ targets: [{ id: "EU", name: "Europe", heading: 48, offsets: [0, 8] }] }),
  $: key => elements[key], document: { contains: () => true },
  api: async () => response,
  fmt: n => Number(n).toFixed(1), css: () => "#888",
  plotLayout: v => v,
  Plotly: { react: async (el, traces, layout) => { drawn = { el, traces, layout }; },
    purge: () => { drawn = null; } }
});
vm.runInContext(source.slice(start, end), context);
const render = vm.runInContext("showElevationPatterns", context);
(async () => {
  await render([{ band: "20", target: "EU", hfta: 11.4, issues: [], i: 0, site: "s1", tower: "w1" }],
    ["s1|w1"], () => "Test site", () => "One tower");
  assert(drawn, "No pattern drawn");
  assert.equal(drawn.traces[0].type, "scatter");
  assert.equal(drawn.traces[0].mode, "lines");
  assert.equal(drawn.traces[0].x.length, 140);
  assert.equal(drawn.traces[0].x[1] - drawn.traces[0].x[0], 0.25);
  assert.equal(drawn.traces[0].y.length, 140);
  assert(Math.max(...drawn.traces[0].y) > Math.min(...drawn.traces[0].y) + 15, "Nulls must remain visible");
  assert(drawn.traces[0].name.includes("FOM 11.4 dB"), drawn.traces[0].name);
  assert.equal(drawn.traces[1].type, "bar");
  assert.equal(drawn.traces[1].y[0], 15);
  assert.equal(drawn.traces[1].y[1], 40);
  assert.equal(drawn.layout.xaxis.range[1], 35);
  assert(note.textContent.includes("0.25°"), note.textContent);
  console.log("PASS: 140-point gain curves retain lobes/nulls, FOM legends, and AoA probability overlay");
})().catch(e => { console.error(e); process.exitCode = 1; });
