// Run with: node tests/test_voacap_targets.cjs
// Execute the actual client helper in an isolated VM; no browser or network required.
const fs = require("fs");
const vm = require("vm");
const assert = require("node:assert/strict");

const source = fs.readFileSync("static/v2.js", "utf8");
const begin = source.indexOf("const REGION = {");
const end = source.indexOf("/* Dialog:", begin);
assert(begin >= 0 && end > begin, "The target helper must remain identifiable");
const code = source.slice(begin, end);
const project = {
  sites: [{ id: "s1", name: "NH", lat: 43.6724, lon: -72.0136 }],
  targets: [{ id: "old", name: "Existing local target", prn: "LOCAL.PRN" }],
  towers: [
    { id: "all", targets: ["old"] },
    { id: "none", targets: [] },
    { id: "implicit" },
  ]
};
let saves = 0, id = 0, queries = 0;
const context = vm.createContext({
  P: () => project,
  S: { prns: [] },
  SLUG: "test",
  save: async () => { saves++; },
  uid: () => `new${++id}`,
  api: async () => { queries++; return { coverage: { "40m": 0.9, "20m": 0.2, "80m": 0.8 } }; },
  $: () => null,
});
vm.runInContext(code, context);
const add = vm.runInContext("addMissingVOACAPTargets", context);
const regionCode = vm.runInContext("regionCode", context);
const bearingTo = vm.runInContext("bearingTo", context);
assert.equal(regionCode("NH-EU-VOACAP.PRN"), "EU");
assert.equal(regionCode("W1-MA-JA.PRN"), "JA");

(async () => {
  const files = [
    { region: "EU", file: "NH-EU-VOACAP.PRN", bands: ["40", "20", "15"] },
    { region: "AS", file: "NH-AS-VOACAP.PRN", bands: ["20"] },
  ];
  let summary = await add(files, { lat: 43.6724, lon: -72.0136 });
  assert.equal(summary.added, 2);
  assert.equal(saves, 1);
  assert.equal(project.targets.length, 3);
  assert.equal(project.targets[0].name, "Existing local target");
  assert.equal(project.targets[1].name, "Europe");
  assert.equal(project.targets[1].prn, "NH-EU-VOACAP.PRN");
  assert.deepEqual([...project.targets[1].bands], ["40", "20", "15"]);
  assert.equal(project.targets[1].heading, bearingTo(43.6724, -72.0136, 50, 10));
  assert.equal(project.targets[2].name, "Asia");
  assert.deepEqual([...project.targets[2].offsets], [-16, -8, 0, 8, 16]);
  assert.deepEqual([...project.targets[2].bands], ["20"]);
  assert.deepEqual([...project.towers[0].targets], ["old", "new1", "new2"]);
  assert.deepEqual([...project.towers[1].targets], []);
  assert.equal(project.towers[2].targets, undefined);

  summary = await add(files);
  assert.equal(summary.added, 0);
  assert.equal(summary.already, 2);
  assert.equal(project.targets.length, 3);
  assert.equal(saves, 1);

  // Previously generated files can be added without rerunning VOACAP.
  summary = await add(["NH-SA-VOACAP.PRN"]);
  assert.equal(summary.added, 1);
  assert.equal(queries, 1);
  assert.deepEqual([...project.targets[3].bands], ["40"]);
  assert.equal(project.targets[3].name, "South America");

  // A preexisting manually configured target prevents a second regional target.
  project.targets.push({ id: "manual", name: "Japan", prn: "W1-MA-JA.PRN" });
  summary = await add([{ file: "NH-JA-VOACAP.PRN", region: "JA", bands: ["20"] }]);
  assert.equal(summary.added, 0);
  assert.equal(summary.already, 1);

  console.log("PASS: batch auto-creates targets, picks bearings/bands, respects tower selections, prevents duplicates, backfills existing files");
})().catch(error => { console.error(error); process.exitCode = 1; });
