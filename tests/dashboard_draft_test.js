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
  thumbTitle: makeInput(), project: makeInput('careyrpg'), purpose: makeInput(),
  srcPreview: { innerHTML: '' },  // uploaded-source preview target (PR#18 upload flow)
};
let slotInputs = [];
const $ = id => fields[id];
const document = { querySelectorAll: sel => (sel === '#slots input' ? slotInputs : []) };
function slotFields() { /* stub: slot inputs are managed by the test */ }
// browser globals the dashboard uses (source-image upload keeps its state on
// window._srcArtifact; applyDraft escapes the preview through esc)
const window = { _srcArtifact: null, _recipes: [] };
const esc = s => String(s == null ? '' : s);

eval(m[0].replace(/\/\* ── end draft-persistence ── \*\//, ''));

// save -> load roundtrip (source image is now an uploaded artifact on window)
slotInputs = [Object.assign(makeInput('S TIER SORCERER'), { dataset: { slot: 'subject' } })];
fields.thumbTitle.value = 'BEST BUILDS';
window._srcArtifact = { id: 'src_abc123', name: 'shot.png' };
fields.purpose.value = 'U1 batch 1';
fields.recipe.value = 'build_guide';
saveDraft();
let d = loadDraft();
check('draft saves recipe/slots/title/srcArtifact/project/purpose',
  d && d.recipe === 'build_guide' && d.slots.subject === 'S TIER SORCERER'
  && d.title === 'BEST BUILDS' && d.srcArtifact && d.srcArtifact.id === 'src_abc123'
  && d.project === 'careyrpg' && d.purpose === 'U1 batch 1');

// apply restores into a fresh form (reload / room-change path)
fields.recipe.value = 'rpg_tier_list';
fields.thumbTitle.value = ''; window._srcArtifact = null; fields.purpose.value = ''; fields.project.value = '';
slotInputs = [Object.assign(makeInput(), { dataset: { slot: 'subject' } })];
applyDraft(loadDraft());
check('applyDraft restores every field incl. uploaded source',
  fields.recipe.value === 'build_guide' && slotInputs[0].value === 'S TIER SORCERER'
  && fields.thumbTitle.value === 'BEST BUILDS'
  && window._srcArtifact && window._srcArtifact.id === 'src_abc123'
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

// ── 2. required-slot contract (the recipe→dashboard fix under test) ──────────
const hm = html.match(/\/\* The recipe currently selected[\s\S]*?function missingRequiredSlots[\s\S]*?\n\}/);
check('required-slot helpers present in the dashboard', !!hm);
if (hm) {
  window._recipes = [{ id: 'yt_thumbnail', version: 4,
    slots: ['game', 'subject', 'emotion', 'composition', 'palette', 'lighting'],
    vary: ['palette', 'lighting', 'composition'] }];
  fields.recipe = { value: 'yt_thumbnail@4', options: [{ value: 'yt_thumbnail@4' }] };
  eval(hm[0]);
  check('emotion renders as a required (non-vary) slot',
    requiredSlots().includes('emotion') && requiredSlots().includes('subject'));
  check('vary-supplied slots are NOT rendered as founder inputs',
    !requiredSlots().includes('palette') && !requiredSlots().includes('lighting')
    && !requiredSlots().includes('composition'));
  check('blank emotion is reported missing before POST',
    missingRequiredSlots({ game: 'Palworld', subject: 'a trainer' }).includes('emotion'));
  check('a filled emotion completes the required set (valid payload)',
    missingRequiredSlots({ game: 'Palworld', subject: 'a trainer', emotion: 'shocked' }).length === 0);
}
check('non-vary slots render as required inputs marked with *',
  /requiredSlots\(r\)\.map[\s\S]{0,220}\*<\/span>[\s\S]{0,120}required/.test(html));
check('submitGen names missing required slots and blocks before POST /jobs',
  /missingRequiredSlots\(d\.slots\)[\s\S]{0,220}throw new Error[\s\S]{0,500}await jpost\('\/jobs'/.test(html));

// ── 3. structural invariants in the page source ─────────────────────────────
check('polling refreshes only #imgOut when the form is on screen',
  /room === 'create' && \$\('genForm'\)[\s\S]{0,700}\$\('imgOut'\)\.innerHTML =/.test(html));
check('full re-render skipped while typing in the view',
  /if \(typingInView\(\)\) return/.test(html));
check('form saves draft on input and change',
  html.includes("$('genForm').addEventListener('input', saveDraft)")
  && html.includes("$('genForm').addEventListener('change', saveDraft)"));
check('draft restored after a full render of the Image Studio',
  /applyDraft\(loadDraft\(\)\)/.test(html));
check('draft cleared only inside successful submitGen (after jpost)',
  /await jpost\('\/jobs'[\s\S]{0,500}clearDraft\(\)/.test(html)
  && (html.match(/clearDraft\(\)/g) || []).length === 2 /* def + submitGen */);
check('no overlapping refresh cycles', /if \(_refreshing\) return/.test(html));
check('recipe change preserves typed slot values', /const keep = \{\}/.test(html));

console.log(failures ? `\n${failures} FAILED` : '\nALL CHECKS PASSED');
process.exit(failures ? 1 : 0);
