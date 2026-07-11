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
};
const window = { _srcArtifact: null };
let slotInputs = [];
const $ = id => fields[id];
const document = { querySelectorAll: sel => (sel === '#slots input' ? slotInputs : []) };
function slotFields() { /* stub: slot inputs are managed by the test */ }

eval(m[0].replace(/\/\* ── end draft-persistence ── \*\//, ''));

// save -> load roundtrip
slotInputs = [Object.assign(makeInput('S TIER SORCERER'), { dataset: { slot: 'subject' } })];
fields.thumbTitle.value = 'BEST BUILDS';
window._srcArtifact = { id: 'art.source.test', name: 'shot.png' };
fields.purpose.value = 'U1 batch 1';
fields.recipe.value = 'build_guide';
saveDraft();
let d = loadDraft();
check('draft saves recipe/slots/title/source-artifact/project/purpose',
  d && d.recipe === 'build_guide' && d.slots.subject === 'S TIER SORCERER'
  && d.title === 'BEST BUILDS' && d.srcArtifact.id === 'art.source.test'
  && d.project === 'careyrpg' && d.purpose === 'U1 batch 1');

// apply restores into a fresh form (reload / room-change path)
fields.recipe.value = 'rpg_tier_list';
fields.thumbTitle.value = ''; fields.purpose.value = ''; fields.project.value = '';
window._srcArtifact = null;
slotInputs = [Object.assign(makeInput(), { dataset: { slot: 'subject' } })];
applyDraft(loadDraft());
check('applyDraft restores every field',
  fields.recipe.value === 'build_guide' && slotInputs[0].value === 'S TIER SORCERER'
  && fields.thumbTitle.value === 'BEST BUILDS' && window._srcArtifact.id === 'art.source.test'
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
  /room === 'image' && \$\('genForm'\)[\s\S]{0,600}\$\('imgOut'\)\.innerHTML =/.test(html));
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
check('Luna Pulse consumes cursor-based job transitions',
  /\/job-updates\?after=/.test(html)
  && /bh_job_event_cursor/.test(html)
  && /latestPerJob/.test(html));
check('Luna Pulse reports running, overdue, completion, retry and review readiness',
  /function pulseText\(update\)/.test(html)
  && /taking longer than expected/.test(html)
  && /failed an attempt and will retry/.test(html)
  && /update\.action === 'job\.done'\) return j\.message/.test(html));
check('trusted Pulse updates appear in chat but are not echoed back into the LLM',
  /systemUpdate:true/.test(html)
  && /!m\.systemUpdate/.test(html)
  && /pushLunaUpdate/.test(html));
check('browser job alerts require a founder gesture and retain in-app fallback',
  /onclick="enableJobNotifications\(\)"/.test(html)
  && /Notification\.requestPermission\(\)/.test(html));

async function runSubmitContractTests() {
  const spec = JSON.parse(fs.readFileSync(
    path.join(__dirname, '..', 'recipes', 'yt_thumbnail.v4.json'), 'utf8'));
  const allSlots = [...new Set([...spec.template.matchAll(/\{(\w+)\}/g)].map(m => m[1]))];
  const recipe = { id:spec.id, version:spec.version, slots:allSlots, vary:Object.keys(spec.vary || {}) };
  const required = recipe.slots.filter(s => !recipe.vary.includes(s));
  function missingRequiredSlots(vals) {
    return required.filter(s => !String((vals && vals[s]) || '').trim());
  }
  check('exact yt_thumbnail@4 contract makes emotion founder-required',
    recipe.id === 'yt_thumbnail' && recipe.version === 4
    && required.includes('emotion') && !recipe.vary.includes('emotion'));
  check('vary-supplied slots are not founder inputs',
    ['palette','lighting','composition'].every(s => recipe.vary.includes(s) && !required.includes(s)));
  check('missing-slot validation names every founder-required field',
    missingRequiredSlots({}).join(', ') === 'game, subject, emotion');
  check('required founder labels are visibly starred',
    /<label>\$\{esc\(s\)\} <span style="color:var\(--red\)">\*<\/span><\/label>/.test(html));

  fields.recipe.value = 'yt_thumbnail@4';
  fields.recipe.options = [{ value:'yt_thumbnail@4' }];
  fields.thumbTitle.value = '';
  fields.project.value = 'careyrpg';
  fields.purpose.value = 'hardware contract regression';
  fields.ckpt = makeInput(); fields.aspect = makeInput(); fields.lora = makeInput();
  fields.enhance = { checked:false }; fields.view = { innerHTML:'form remains' };
  slotInputs = [
    Object.assign(makeInput('Palworld'), { dataset:{ slot:'game' } }),
    Object.assign(makeInput('a Pal trainer'), { dataset:{ slot:'subject' } }),
    Object.assign(makeInput(''), { dataset:{ slot:'emotion' } }),
  ];
  window._srcArtifact = null;
  let said = '';
  const posts = [];
  const say = value => { said = value; };
  const jpost = async (url, body) => { posts.push({url, body}); return {id:'job.valid'}; };
  const render = () => {};
  const submitStart = html.indexOf('async function submitGen()');
  const submitEnd = html.indexOf('/* ── Operator Chat', submitStart);
  check('submitGen source extracted for behavioural contract test',
    submitStart >= 0 && submitEnd > submitStart);
  const submitSource = html.slice(submitStart, submitEnd).trim();
  const submitGen = eval('(' + submitSource + ')');

  saveDraft();
  await submitGen();
  check('blank emotion blocks submit before POST and names every missing field',
    posts.length === 0 && said === 'error: Missing required fields: emotion');
  check('validation failure preserves draft and typed values',
    loadDraft() !== null && slotInputs[0].value === 'Palworld'
    && slotInputs[1].value === 'a Pal trainer' && fields.view.innerHTML === 'form remains');

  slotInputs[2].value = 'wide-eyed shock';
  saveDraft();
  await submitGen();
  check('filled emotion creates one valid pinned payload',
    posts.length === 1 && posts[0].url === '/jobs'
    && posts[0].body.payload.recipe === 'yt_thumbnail@4'
    && posts[0].body.payload.slots.emotion === 'wide-eyed shock'
    && posts[0].body.payload.slots.game === 'Palworld');
  check('successful POST clears the draft', loadDraft() === null);
}

runSubmitContractTests().catch(e => {
  console.error(e); failures++;
}).finally(() => {
  console.log(failures ? `\n${failures} FAILED` : '\nALL CHECKS PASSED');
  process.exit(failures ? 1 : 0);
});
