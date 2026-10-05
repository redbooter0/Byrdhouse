'use strict';
const $ = id => document.getElementById(id);
let preset = 'photo', studioState = null, lastJobs = '', busy = false;
let defaultsApplied = false;
const stateLabels = {queued:'Queued',running:'Rendering locally',recovering:'Reconnecting to the existing render',needs_review:'Ready for your review',approved:'Kept',rejected:'Rejected',failed:'Render failed'};

async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : {
    method:'POST', headers:{'Content-Type':'application/json','X-ByrdHouse-Studio':'1'}, body:JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'The local request failed.');
  return data;
}
function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}
function error(message) {
  $('formError').textContent = message || '';
  $('formError').hidden = !message;
}
function identityNote() {
  const flux = $('engine').value === 'flux';
  const identityMode = $('identityMode').value;
  const exact = identityMode === 'photo_edit';
  const faceId = identityMode === 'reference';
  const instantId = identityMode === 'instantid';
  const pulid = identityMode === 'pulid';
  const animeAnchor = identityMode === 'anime_anchor';
  const selected = $('lora').value;
  const reference = flux || exact || faceId || instantId || pulid || animeAnchor;
  const referenceLabel = document.querySelector('label[for="reference"]');
  if (referenceLabel) referenceLabel.textContent = animeAnchor ? 'Pose / framing guide' : 'Your photo';
  $('sourceMaskButton').textContent = animeAnchor ? 'Analyze Anime Canon Cutout' : 'Analyze photo for scene edit';
  $('identityTitle').textContent = flux ? 'Your original photo anchors Carey' : exact ? 'Photo variation uses your original' : animeAnchor ? 'Carey Anime Canon Anchor drives the episode frame' : pulid ? 'PuLID uses Carey’s fixed three-photo board' : instantId ? 'InstantID tests a new Carey pose or scene' : faceId ? 'Your photo guides a new Carey scene' : selected ? 'Carey model selected' : 'Carey model is missing';
  $('identityNote').textContent = flux ? 'Keep your face, Black identity, skin tone and hair while changing the scene. Compare every result with your photo.' : exact
    ? 'Diffusion can change facial features even at low denoise. This mode does not guarantee an exact replica; compare every feature with your original.' : animeAnchor
    ? 'The locked Carey Anime Canon Anchor supplies the character. Choose a photo or the anchor below only for pose/framing; start with the anchor for close canonical portraits. Inspect the afro silhouette, high forehead, brows, eyes, beard, and linework before keeping it.' : pulid
    ? 'Uses the frozen neutral, smile, and night Carey photo board with a separate real full-body Carey pose source. It creates a new scene; inspect hairline, jaw, eyes, nose, mouth, and skin tone before keeping it.' : faceId
    ? 'FaceID Plus V2 uses your face reference for a new pose, outfit, and background. Compare every result with your original photo.' : selected
    ? 'Your Black identity and the trained trigger are included automatically. Compare the result with your original photo.'
    : 'Install your Carey identity model before generating character versions.';
  $('strength').disabled = flux || exact || !selected;
  $('sdxlModel').hidden = flux || exact; $('sdxlMethod').hidden = flux;
  $('photoStrengthRow').hidden = flux || exact || pulid || animeAnchor;
  $('engineTag').textContent = flux ? 'FLUX.2' : 'SDXL';
  $('mode').disabled = flux;
  if (flux) $('mode').value = 'fast';
  $('referenceControls').hidden = !reference;
  if ($('reference').value) $('referencePreview').src = '/references/' + $('reference').value;
}
function engineReady() {
  if (!studioState || !studioState.connected) return false;
  if ($('engine').value === 'flux') return studioState.flux_ready;
  const mode = $('identityMode').value;
  if (mode === 'photo_edit') return studioState.base_ready && (studioState.references || []).length > 0;
  if (mode === 'reference') return studioState.base_ready && studioState.reference_ready;
  if (mode === 'instantid') return studioState.base_ready && studioState.instantid_ready;
  if (mode === 'pulid') return studioState.pulid_ready;
  if (mode === 'anime_anchor') return studioState.anime_ready;
  return studioState.base_ready && $('lora').value;
}
function updateRecipe() {
  const recipe = studioState && studioState.recipes.find(row => row.id === $('recipe').value);
  $('prompt').required = !recipe;
  $('versions').disabled = !recipe;
  $('recipeDescription').textContent = recipe ? recipe.description : 'Describe your scene. Carey’s identity is included automatically.';
  $('generateLabel').textContent = recipe ? `Generate ${recipe.count * Number($('versions').value)} Carey stills` : 'Generate Carey image';
}
async function refreshState() {
  try {
    studioState = await api('/api/state');
    const ready = studioState.connected && (studioState.base_ready || studioState.flux_ready);
    $('connection').className = 'connection ' + (ready ? 'online' : 'offline');
    const training = studioState.training || {};
    const trainingActive = ['loading','training'].includes(training.state);
    $('connection').replaceChildren(node('i'), document.createTextNode(trainingActive ? 'Training Carey locally' : ready ? 'Local GPU studio connected' : studioState.connected ? 'Model setup pending' : 'ComfyUI offline'));
    $('trainingStatus').textContent = trainingActive ? (training.step ? `Training ${training.step} / ${training.steps} steps` : 'Preparing your Carey model…') : training.state === 'trained_needs_review' ? 'Carey model trained. Each new version needs a likeness review.' : 'Training is pending. Adding photos does not start training.';
    $('comfyLink').href = studioState.comfy_url;
    $('photoCount').textContent = studioState.photo_count;
    $('photoPath').textContent = studioState.photo_dir;
    $('outputPath').textContent = 'Saved to ' + studioState.output_dir;
    const selected = $('lora').value;
    const names = (studioState.loras || []).filter(name => /carey/i.test(name));
    if (JSON.stringify(names) !== $('lora').dataset.models) {
      $('lora').replaceChildren();
      names.forEach(name => $('lora').add(new Option(name.replace(/\.safetensors$/i,'').replace(/carey_sdxl_v1_preview/,'Carey v1 · older preview').replace(/carey_sdxl_v2_full/,'Carey v2 · full photo set'),name)));
      $('lora').value = names.includes(selected) ? selected : studioState.identity_lora;
      $('lora').dataset.models = JSON.stringify(names);
      identityNote();
    }
    if (!defaultsApplied) {
      (studioState.references || []).forEach(row => $('reference').add(new Option(row.label,row.id)));
      $('reference').value = studioState.default_reference;
      (studioState.recipes || []).forEach(row => $('recipe').add(new Option(`${row.title} · ${row.count} shots`,row.id)));
      if (!Array.from($('identityMode').options).some(option => option.value === 'pulid')) {
        $('identityMode').add(new Option('PuLID private lab · Carey pose + new scene','pulid'), 0);
      }
      if (!Array.from($('identityMode').options).some(option => option.value === 'anime_anchor')) {
        $('identityMode').add(new Option('Carey Anime Canon · episode keyframe','anime_anchor'), 0);
      }
      $('identityMode').value = studioState.default_identity_mode;
      $('mode').value = studioState.default_mode || 'quality';
      $('strength').value = studioState.default_lora_strength;
      $('strengthValue').textContent = Number($('strength').value).toFixed(2);
      $('mode').querySelector('option[value="fast"]').textContent = studioState.fast_checkpoint ? 'Fast photoreal · 5 steps' : 'Fast · 4 steps';
      $('identityMode').querySelector('option[value="lora"]').disabled = !!studioState.require_carey_reference;
      $('referenceStrength').value = studioState.default_reference_strength;
      $('referenceStrengthValue').textContent = Number($('referenceStrength').value).toFixed(2);
      $('engine').value = studioState.default_engine || 'sdxl';
      defaultsApplied = true;
      updateRecipe(); identityNote();
    }
    [...$('identityMode').options].forEach(option => {
      option.disabled = option.value === 'reference' && !studioState.reference_ready;
      if (option.value === 'instantid') option.disabled = !studioState.instantid_ready;
      if (option.value === 'pulid') option.disabled = !studioState.pulid_ready;
      if (option.value === 'anime_anchor') option.disabled = !studioState.anime_ready;
      if (option.value === 'lora') option.disabled = !!studioState.require_carey_reference;
    });
    if (studioState.require_carey_reference && $('identityMode').value === 'lora') $('identityMode').value = 'photo_edit';
    $('engine').querySelector('option[value="flux"]').disabled = !studioState.flux_ready;
    $('animatePhotoButton').disabled = !(studioState.references || []).length;
    $('animateSceneButton').disabled = !studioState.wan22_ready;
    $('sourceMaskButton').disabled = !studioState.source_mask_ready;
    identityNote();
    $('generateButton').disabled = busy || !engineReady();
    $('generateButton').title = engineReady() ? '' : studioState.error || 'The selected image engine or Carey reference is unavailable.';
    $('mode').options[0].disabled = !studioState.fast_ready;
    if (ready && !studioState.fast_ready) $('mode').value = 'quality';
  } catch (exc) {
    $('connection').className = 'connection offline';
    $('connection').replaceChildren(node('i'),document.createTextNode('Studio disconnected'));
  }
}
async function review(job, state) {
  try { await api('/api/jobs/' + job.id + '/review', {state}); await refreshJobs(); }
  catch(exc) { error(exc.message); }
}
function reuse(job) {
  $('engine').value = job.engine || 'sdxl';
  $('prompt').value = job.prompt;
  $('recipe').value = ''; updateRecipe();
  $('mode').value = job.mode;
  $('aspect').value = job.aspect;
  $('seed').value = job.seed;
  if ([...$('lora').options].some(option => option.value === job.lora)) $('lora').value = job.lora;
  $('strength').value = job.strength;
  $('strengthValue').textContent = Number(job.strength).toFixed(2);
  $('identityMode').value = ['lora','reference','instantid','pulid','anime_anchor','photo_edit'].includes(job.identity_mode) ? job.identity_mode : 'photo_edit';
  if (job.reference) $('reference').value = job.reference;
  $('referenceStrength').value = job.reference_strength || 0.7;
  $('referenceStrengthValue').textContent = Number($('referenceStrength').value).toFixed(2);
  choosePreset(job.preset);
  identityNote();
  $('prompt').focus();
  $('createTitle').scrollIntoView({behavior:'smooth',block:'start'});
}
function imageCard(job, imageUrl) {
  const card = node('article','image-card');
  const animation = ['portrait_animation','scene_animation'].includes(job.operation);
  const continuity = job.operation === 'anime_review';
  const mask = job.operation === 'source_mask';
  const preserved = job.operation === 'source_preserve';
  const picture = node('button','image-button');
  picture.type = 'button';
  const image = node('img'); image.src = imageUrl; image.alt = job.prompt; image.loading = 'lazy';
  picture.append(image);
  picture.addEventListener('click',() => {
    $('largeImage').src = imageUrl; $('largeImage').alt = job.prompt;
    $('comparisonReference').src = continuity ? '/api/jobs/'+job.id+'/matched-reference' : job.reference_snapshot ? '/api/jobs/'+job.id+'/source' : '/references/' + (job.reference || $('reference').value || 'neutral');
    $('largePrompt').textContent = job.prompt; $('imageDialog').showModal();
  });
  const content = node('div','card-content');
  if (job.variant) content.append(node('strong','variant-label',job.variant + ' · version ' + job.version));
  content.append(node('p','',job.prompt));
  const meta = node('div','card-meta');
  meta.append(node('span','',mask ? 'PHOTO PROTECTION · REVIEW COVERAGE' : preserved ? 'ORIGINAL PIXELS · SCENE EDIT' : animation ? 'PORTRAIT MOTION · 2.9 SEC' : job.operation === 'identity_belt' ? 'CORRECTED CAREY CANDIDATE' : job.engine === 'flux' ? 'FLUX PHOTO EDIT · 4 STEPS' : job.identity_mode === 'anime_anchor' ? 'CAREY ANIME CANON · EPISODE KEYFRAME' : job.identity_mode === 'pulid' ? 'PULID + REAL CAREY POSE · PRIVATE LAB' : job.identity_mode === 'photo_edit' ? `PHOTO VARIATION · ${Math.round((job.denoise || 0.5) * 100)}%` : job.identity_mode === 'reference' ? (job.mode === 'fast' ? 'SDXL FACEID FAST' : 'SDXL FACEID · 24 STEPS') : job.mode === 'fast' ? 'SDXL FAST' : 'SDXL QUALITY · 24 STEPS'),
    node('span','',(continuity ? job.review_wall_seconds : job.seconds) == null ? '' : (continuity ? job.review_wall_seconds : job.seconds).toFixed(1) + ' sec'));
  content.append(meta);
  if (job.operation === 'scene_animation') meta.firstChild.textContent = 'CAREY SCENE MOTION · REVIEW PREVIEW';
  if (continuity) {
    meta.firstChild.textContent = 'CAREY LIKENESS CHECK · READ ONLY';
    const summary = job.review_summary;
    if (summary) {
      content.append(node('p','small',`${summary.frames_examined}/${summary.total_frames} saved frames examined against the ${summary.selected_view} view. Source approval is unchanged.`));
      const findings = node('ul','small');
      Object.entries(summary.feature_counts).forEach(([feature, counts]) => {
        findings.append(node('li','',`${feature}: ${counts.change} flagged, ${counts.inconclusive} inconclusive, ${counts.review} measured for visual review`));
      });
      content.append(findings,node('p','small','These checks do not prove exact likeness. Inspect eyes, beard, teeth, mouth and motion directly.'));
    }
  }
  if (job.operation === 'scene_animation') content.append(node('p','small','Short scene-motion candidate. Check every frame for changes to the face and hair; this preview needs your review.'));
  if (preserved) content.append(node('p','small','Carey’s opaque face, hair interior and clothing pixels are retained. Inspect the soft hair edge and scene seams before keeping or animating.'));
  const actions = node('div','card-actions');
  const download = node('a','','Save'); download.href = imageUrl; download.download = 'byrdhouse-' + job.id + '.png';
  if (animation) { download.textContent='Save video'; download.href=job.video_url; download.download='carey-'+job.id+'.mp4'; }
  const settings = node('button','','Reuse settings'); settings.type = 'button'; settings.addEventListener('click',() => reuse(job));
  const check = node('button','','Correct likeness'); check.type = 'button';
  check.addEventListener('click',() => {
    const index = job.images.indexOf(imageUrl) + 1;
    $('beltTarget').value = `${job.id}_${index}.png`;
    if (job.reference) $('reference').value = job.reference;
    $('beltTarget').scrollIntoView({behavior:'smooth',block:'center'});
    if (!$('beltButton').disabled) $('beltButton').click();
  });
  const keep = node('button','',mask ? 'Accept mask coverage' : animation ? 'Keep motion' : 'Keep likeness'); keep.type = 'button'; keep.addEventListener('click',() => review(job,'approved'));
  const reject = node('button','','Reject'); reject.type = 'button'; reject.addEventListener('click',() => review(job,'rejected'));
  const metadata = node('a','','Metadata'); metadata.href = job.metadata_url; metadata.target='_blank'; metadata.rel='noopener';
  actions.append(download);
  if (!animation && !mask && !continuity) {
    if (!preserved && job.operation !== 'identity_belt') actions.append(settings);
    if (!preserved) actions.append(check);
    const animate = node('button','','Animate still'); animate.type='button';
    animate.disabled = job.state !== 'approved';
    animate.title = animate.disabled ? 'Review this still and Keep likeness first.' : 'Gentle blink and head movement';
    animate.addEventListener('click',() => queueAnimation({source_job_id:job.id},animate));
    actions.append(animate);
    if (studioState.wan22_ready) {
      const scene = node('button','','Preview scene motion'); scene.type='button';
      scene.disabled = job.state !== 'approved';
      scene.title = scene.disabled ? 'Keep likeness after reviewing the still first.' : 'Short movement preview from this still';
      scene.addEventListener('click',() => queueAnimation({source_job_id:job.id},scene,true));
      actions.append(scene);
    }
  }
  if (mask) {
    const edit = node('button','','Edit '+job.region+' with this mask'); edit.type='button';
    edit.disabled = job.state !== 'approved';
    edit.title = 'Inspect the green protected head and all curls, then Accept mask coverage. Enter scene direction in the form.';
    edit.addEventListener('click',async () => {
      edit.disabled=true;
      try {
        await api('/api/source-edits',{mask_job_id:job.id,prompt:$('prompt').value,seed:$('seed').value.trim()||null});
        $('sourceMaskStatus').textContent='Scene edit queued. The original pose and protected pixels are retained; inspect the finished scene before animation.';
        $('packFilter').value=''; lastJobs=''; await refreshJobs();
      } catch(exc) { error(exc.message); edit.disabled=false; }
    });
    actions.append(edit);
  }
  const illustrated = job.identity_mode === 'anime_anchor' || job.identity_mode === 'anime_source_preserve'
    || job.preset === 'anime' || animation && job.reference === 'carey-anime-anchor';
  if (illustrated && !mask && !continuity) {
    const angle = node('select'); angle.setAttribute('aria-label','Visible angle for likeness check');
    [['three-quarter','Three-quarter'],['front','Front'],['facing-right','Facing right'],['facing-left','Facing left'],['back','Back']]
      .forEach(([value,label]) => angle.add(new Option(label,value)));
    const examine = node('button','','Check likeness'); examine.type='button';
    examine.addEventListener('click',async () => {
      examine.disabled=true;
      try {
        await api('/api/anime-reviews',{source_job_id:job.id,view:angle.value,image_index:job.images.indexOf(imageUrl)});
        $('packFilter').value=''; lastJobs=''; await refreshJobs();
      } catch(exc) { error(exc.message); examine.disabled=false; }
    });
    actions.append(angle,examine);
  }
  if (continuity) {
    const report = node('a','','Complete frame findings'); report.href='/api/jobs/'+job.id+'/continuity';
    report.target='_blank'; report.rel='noopener'; actions.append(report,metadata);
  } else actions.append(keep,reject,metadata);
  if (job.belt_analysis) {
    const analysis = node('a','','Hairline and jaw checks');
    analysis.href = '/api/belt/' + encodeURIComponent(job.belt_analysis);
    analysis.target = '_blank'; analysis.rel = 'noopener'; actions.append(analysis);
  }
  content.append(actions);
  content.append(node('span','review-state ' + job.state,continuity ? 'Check complete · source review unchanged' : mask && job.state === 'approved' ? 'Mask coverage accepted' : stateLabels[job.state] || job.state));
  if (animation) {
    const video=node('video','motion-preview'); video.src=job.video_url;
    video.poster=imageUrl; video.controls=true; video.loop=true; video.playsInline=true; video.preload='metadata';
    video.setAttribute('aria-label','Carey portrait motion preview');
    card.append(video);
    const compare=node('button','secondary-button','Compare source'); compare.type='button';
    compare.addEventListener('click',() => picture.click()); actions.append(compare);
  } else card.append(picture);
  card.append(content); return card;
}

async function queueAnimation(payload, button, scene = false) {
  button.disabled=true; $('animationStatus').textContent='Queueing your local motion preview…';
  try {
    await api(scene ? '/api/scene-animations' : '/api/animations',payload);
    $('animationStatus').textContent='Queued. Your video will appear in the gallery; check the face throughout the motion.';
    lastJobs=''; await refreshJobs();
  } catch(exc) { $('animationStatus').textContent=exc.message; }
  finally { button.disabled=false; }
}
$('animatePhotoButton').addEventListener('click',() => queueAnimation({reference:$('reference').value},$('animatePhotoButton')));
$('animateSceneButton').addEventListener('click',() => queueAnimation({reference:$('reference').value},$('animateSceneButton'),true));
$('sourceMaskButton').addEventListener('click',async () => {
  $('sourceMaskButton').disabled=true; $('sourceMaskStatus').textContent='Queueing semantic photo analysis…';
  try {
    await api('/api/source-masks',{reference:$('reference').value,region:'background'});
    $('sourceMaskStatus').textContent=$('identityMode').value === 'anime_anchor'
      ? 'Queued. Inspect the full afro, face, beard, shirt and soft alpha edge before accepting the canon cutout.'
      : 'Queued. Inspect green face and hair coverage plus the soft alpha edge before accepting the mask.';
    $('packFilter').value=''; lastJobs=''; await refreshJobs();
  } catch(exc) { $('sourceMaskStatus').textContent=exc.message; }
  finally { $('sourceMaskButton').disabled=!studioState?.source_mask_ready; }
});
async function refreshJobs() {
  try {
    const [result,packResult] = await Promise.all([api('/api/jobs'),api('/api/packs')]);
    const fingerprint = JSON.stringify([result,packResult,$('packFilter').value,$('showRejected').checked]);
    if (fingerprint === lastJobs) return;
    lastJobs = fingerprint;
    const jobs = result.jobs;
    const latestSource = jobs.find(job => ['source_mask','source_preserve'].includes(job.operation));
    if (latestSource) {
      $('sourceMaskStatus').textContent = latestSource.operation === 'source_mask'
        ? latestSource.state === 'approved' ? 'Mask coverage accepted. Enter background direction, then edit from the mask card. Inspect the finished hair boundary.'
          : latestSource.state === 'needs_review' ? 'Photo analysis is ready. Inspect green head coverage, outer curls and the soft alpha edge before accepting the mask.'
          : (stateLabels[latestSource.state] || latestSource.state) + ' · photo protection analysis.'
        : latestSource.state === 'rejected' ? 'Scene edit rejected. Check and improve the hair boundary before using a scene for animation.'
          : (stateLabels[latestSource.state] || latestSource.state) + ' · scene edit. Inspect the face, curls and seams before animation.';
    }
    const packs = packResult.packs || [];
    const packChoice = $('packFilter').value;
    $('packFilter').replaceChildren(new Option('All candidates',''));
    packs.forEach(pack => $('packFilter').add(new Option(pack.title + ' · ' + pack.id.slice(0,6),pack.id)));
    $('packFilter').value = packChoice;
    $('packList').replaceChildren();
    packs.slice(0,5).forEach(pack => {
      const completed = pack.jobs.filter(job => job.images.length).length;
      const activePack = pack.jobs.some(job => ['queued','running','recovering'].includes(job.state));
      const card = node('div','pack-summary');
      const info = node('div'); info.append(node('strong','',pack.title),node('small','',`${completed}/${pack.jobs.length} images · ${activePack ? 'generating' : 'review candidates'}`));
      const view = node('button','secondary-button','View'); view.type='button'; view.addEventListener('click',() => { $('packFilter').value=pack.id; lastJobs=''; refreshJobs(); });
      card.append(info,view);
      if (!activePack && completed) { const download=node('a','secondary-button','Download stills'); download.href='/api/packs/'+pack.id+'/download'; download.download='carey-'+pack.id+'.zip'; card.append(download); }
      $('packList').append(card);
    });
    const active = jobs.filter(job => ['queued','running','recovering'].includes(job.state));
    const failed = jobs.filter(job => job.state === 'failed').slice(0,2);
    const shownJobs = packChoice ? (packs.find(pack => pack.id === packChoice)?.jobs || []) : jobs;
    const images = shownJobs.filter(job => job.images.length && ($('showRejected').checked || job.state !== 'rejected'));
    $('queueStatus').textContent = active.length ? active.length + ' in queue · one render at a time' : 'Ready when you are';
    $('queueList').replaceChildren();
    [...active,...failed].forEach(job => {
      const row = node('div','queue-item ' + job.state);
      const details = node('div');
      details.append(node('strong','',job.operation === 'anime_review' && job.state === 'running' ? 'Checking likeness locally' : stateLabels[job.state]),node('p','',job.prompt));
      if (job.review_progress) details.append(node('p','small',`${job.review_progress.completed}/${job.review_progress.total} frames examined`));
      if (job.error) {
        const diagnostic=node('details'); diagnostic.append(node('summary','','Failure details'),node('p','',job.error));
        details.append(diagnostic);
      }
      row.append(details);
      if (job.state === 'failed' && job.prompt_id) {
        const recover = node('button','secondary-button','Recover existing render'); recover.type='button';
        recover.title = 'Check the saved ComfyUI submission and collect its outputs without another render.';
        recover.addEventListener('click',async () => {
          recover.disabled=true;
          try { await api('/api/jobs/'+job.id+'/recover',{}); lastJobs=''; await refreshJobs(); }
          catch(exc) { error(exc.message); recover.disabled=false; }
        });
        row.append(recover);
      }
      if (job.state === 'running') row.append(node('span','spinner'));
      $('queueList').append(row);
    });
    $('gallery').replaceChildren();
    images.forEach(job => job.images.forEach(url => $('gallery').append(imageCard(job,url))));
    $('imageCount').textContent = images.reduce((count,job) => count + job.images.length,0);
    $('emptyState').hidden = images.length > 0;
  } catch(exc) { /* The connection badge reports service restarts. */ }
}
function choosePreset(value) {
  preset = value;
  document.querySelectorAll('[data-preset]').forEach(button => {
    const selected = button.dataset.preset === value;
    button.classList.toggle('selected',selected); button.setAttribute('aria-pressed',String(selected));
  });
}
document.querySelectorAll('[data-preset]').forEach(button => button.addEventListener('click',() => choosePreset(button.dataset.preset)));
$('strength').addEventListener('input',() => { $('strengthValue').textContent = Number($('strength').value).toFixed(2); });
$('lora').addEventListener('change',identityNote);
$('engine').addEventListener('change',() => { identityNote(); $('generateButton').disabled = busy || !engineReady(); });
$('identityMode').addEventListener('change',identityNote);
$('reference').addEventListener('change',identityNote);
$('referenceStrength').addEventListener('input',() => { $('referenceStrengthValue').textContent=Number($('referenceStrength').value).toFixed(2); });
$('beltButton').addEventListener('click',async () => {
  const target = $('beltTarget').value.trim();
  if (!target) { $('beltStatus').textContent = 'Enter a PNG filename from the ByrdHouse image or photo folder.'; return; }
  $('beltButton').disabled = true; $('beltStatus').textContent = 'Queueing your likeness correction…'; $('beltPreview').hidden = true; $('beltDownload').hidden = true;
  if ($('beltAnalysis')) $('beltAnalysis').remove();
  try {
    await api('/api/belt',{target,reference:$('reference').value || (studioState && studioState.default_reference),label:'studio-belt'});
    $('packFilter').value = '';
    $('beltStatus').textContent = 'Queued with your other renders. The corrected candidate and hairline/jaw report will appear in the gallery for your review.';
    lastJobs = ''; await refreshJobs();
  } catch (exc) { $('beltStatus').textContent = exc.message; }
  finally { $('beltButton').disabled = false; }
});
$('recipe').addEventListener('change',() => { if ($('recipe').value==='anime') choosePreset('anime'); else if ($('recipe').value==='expressions' || $('recipe').value==='angles') choosePreset('photo'); else if ($('recipe').value) choosePreset('cinematic'); updateRecipe(); });
$('versions').addEventListener('change',updateRecipe);
$('packFilter').addEventListener('change',() => { lastJobs=''; refreshJobs(); });
$('showRejected').addEventListener('change',() => { lastJobs=''; refreshJobs(); });
$('generateForm').addEventListener('submit',async event => {
  event.preventDefault(); if (busy) return;
  error(''); busy = true; $('generateButton').disabled = true;
  try {
    const settings={prompt:$('prompt').value,preset,engine:$('engine').value,mode:$('mode').value,aspect:$('aspect').value,
      lora:$('lora').value,strength:Number($('strength').value),seed:$('seed').value.trim() || null,
      identity_mode:$('identityMode').value,reference:$('reference').value,reference_strength:Number($('referenceStrength').value),denoise:0.45};
    if ($('recipe').value) {
      const pack=await api('/api/packs',{...settings,recipe:$('recipe').value,versions:Number($('versions').value)});
      $('packFilter').add(new Option(pack.title,pack.id)); $('packFilter').value=pack.id; lastJobs='';
    } else await api('/api/jobs',settings);
    await refreshJobs();
  } catch(exc) { error(exc.message); }
  finally { busy = false; $('generateButton').disabled = !engineReady(); }
});
$('tryPrompt').addEventListener('click',() => {
  $('prompt').value = 'Head and shoulders portrait in a warm creative studio, relaxed smile, plain black t-shirt, soft window light';
  $('prompt').focus();
});
$('copyPhotoPath').addEventListener('click',async () => {
  if (!studioState) return;
  try { await navigator.clipboard.writeText(studioState.photo_dir); $('copyPhotoPath').textContent = 'Copied · paste in Explorer';
    setTimeout(() => { $('copyPhotoPath').textContent = 'Copy folder path'; },3000);
  } catch(exc) { error('Select and copy the photo folder path shown below.'); }
});
$('closeDialog').addEventListener('click',() => $('imageDialog').close());
$('imageDialog').addEventListener('click',event => { if (event.target === $('imageDialog')) $('imageDialog').close(); });
choosePreset('photo'); updateRecipe(); identityNote(); refreshState(); refreshJobs();
setInterval(refreshJobs,2000); setInterval(refreshState,10000);
