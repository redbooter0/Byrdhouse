// Deterministic verification for the Image Studio draft-persistence fix.
// Run: node tests/dashboard_draft_test.js   (no dependencies, exit 0/1)
//
// 1. Extracts the draft-persistence block from dashboard/index.html and
//    unit-tests save/load/apply/clear semantics against a stubbed DOM.
// 2. Asserts the structural invariants that keep the form alive under
//    polling: partial output refresh, focused-input guard, input->save
//    listeners, clear-only-after-successful-queue, no overlapping ticks.

const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, '..', 'dashboard', 'index.html'), 'utf8');
let failures = 0;
function check(name, cond) {
  console.log(`  [${cond ? 'PASS' : 'FAIL'}] ${name}`);
  if (!cond) failures++;
}

// ── 1. behavioural tests on the extracted draft block ───────────────────────
const m = html.match(/\/\* ── draft-persistence[\s\S]*?\/\* ── end draft-persistence ── \*\//);
check('draft-persistence block present', !!m);

// minimal DOM stubs
const store = {};
const localStorage = {
  setItem: (k, v) => { store[k] = String(v); },
  getItem: k => (k in store ? store[k] : null),
  removeItem: k => { delete store[k]; },
};
function makeInput(v = '') { return { value: v, dataset: {} }; }
const fields = {
  recipe: { value: 'rpg_tier_list', options: [{ value: 'rpg_tier_list' }, { value: 'build_guide' }] },
  thumbTitle: makeInput(), srcImage: makeInput(), project: makeInput('careyrpg'), purpose: makeInput(),
};
let slotInputs = [];
const $ = id => fields[id];
const document = { querySelectorAll: sel => (sel === '#slots input' ? slotInputs : []) };
function slotFields() { /* stub: slot inputs are managed by the test */ }

eval(m[0].replace(/\/\* ── end draft-persistence ── \*\//, ''));

// save -> load roundtrip
slotInputs = [Object.assign(makeInput('S TIER SORCERER'), { dataset: { slot: 'subject' } })];
fields.thumbTitle.value = 'BEST BUILDS';
fields.srcImage.value = 'E:\\captures\\shot.png';
fields.purpose.value = 'U1 batch 1';
fields.recipe.value = 'build_guide';
saveDraft();
let d = loadDraft();
check('draft saves recipe/slots/title/src/project/purpose',
  d && d.recipe === 'build_guide' && d.slots.subject === 'S TIER SORCERER'
  && d.title === 'BEST BUILDS' && d.src === 'E:\\captures\\shot.png'
  && d.project === 'careyrpg' && d.purpose === 'U1 batch 1');

// apply restores into a fresh form (reload / room-change path)
fields.recipe.value = 'rpg_tier_list';
fields.thumbTitle.value = ''; fields.srcImage.value = ''; fields.purpose.value = ''; fields.project.value = '';
slotInputs = [Object.assign(makeInput(), { dataset: { slot: 'subject' } })];
applyDraft(loadDraft());
check('applyDraft restores every field',
  fields.recipe.value === 'build_guide' && slotInputs[0].value === 'S TIER SORCERER'
  && fields.thumbTitle.value === 'BEST BUILDS' && fields.srcImage.value === 'E:\\captures\\shot.png'
  && fields.purpose.value === 'U1 batch 1' && fields.project.value === 'careyrpg');

// a recipe that no longer exists is ignored, everything else still applies
localStorage.setItem('bh_draft', JSON.stringify({ recipe: 'gone', slots: {}, title: 't', project: 'p', purpose: 'x' }));
applyDraft(loadDraft());
check('unknown recipe ignored, other fields still restored',
  fields.recipe.value === 'build_guide' && fields.purpose.value === 'x');

// corrupt storage never throws
localStorage.setItem('bh_draft', '{not json');
check('corrupt draft returns null (no crash)', loadDraft() === null);

// clear removes the draft
saveDraft(); clearDraft();
check('clearDraft empties storage', loadDraft() === null);

// ── 2. structural invariants in the page source ─────────────────────────────
check('polling refreshes only #imgOut when the form is on screen',
  /room === 'image' && \$\('genForm'\)[\s\S]{0,200}\$\('imgOut'\)\.innerHTML = await imgOutHtml\(\)/.test(html));
check('full re-render skipped while typing in the view',
  /if \(typingInView\(\)\) return/.test(html));
check('form saves draft on input and change',
  html.includes("$('genForm').addEventListener('input', saveDraft)")
  && html.includes("$('genForm').addEventListener('change', saveDraft)"));
check('draft restored after a full render of the Image Studio',
  /applyDraft\(loadDraft\(\)\)/.test(html));
check('draft cleared only inside successful submitGen (after jpost)',
  /await jpost\('\/jobs'[\s\S]{0,220}clearDraft\(\)/.test(html)
  && (html.match(/clearDraft\(\)/g) || []).length === 2 /* def + submitGen */);
check('no overlapping refresh cycles', /if \(_refreshing\) return/.test(html));
check('recipe change preserves typed slot values', /const keep = \{\}/.test(html));

console.log(failures ? `\n${failures} FAILED` : '\nALL CHECKS PASSED');
process.exit(failures ? 1 : 0);
