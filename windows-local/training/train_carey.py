"""Local SDXL identity LoRA. Frozen encoders/VAE; cached latents; AMD PyTorch.

The current preview uses all 19 local original photos. There is no held-out
evaluation set in this run. No generated images enter training.
Uses Diffusers/PEFT public APIs and exports Kohya keys for ComfyUI.
"""
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
os.environ['HF_HOME'] = str(ROOT / 'training' / 'hf-cache')
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
import argparse, gc, json, random, time
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageOps
from diffusers import StableDiffusionXLPipeline, DDPMScheduler
from diffusers.utils import convert_state_dict_to_diffusers, convert_all_state_dict_to_peft, convert_state_dict_to_kohya
from peft import LoraConfig
from peft.utils import get_peft_model_state_dict
from safetensors.torch import save_file

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps', type=int, default=600)
    parser.add_argument('--resolution', type=int, default=768)
    args = parser.parse_args()
    if not torch.cuda.is_available(): raise RuntimeError('AMD GPU unavailable')
    torch.manual_seed(20261002); random.seed(20261002)
    out = ROOT / 'training' / 'carey' / 'candidate-v1'
    out.mkdir(parents=True, exist_ok=True)
    status_path = out / 'status.json'
    def status(**kw):
        status_path.write_text(json.dumps(kw, indent=2), encoding='utf-8')
    status(state='loading', steps=args.steps)
    cfg = json.loads((ROOT / 'byrdhouse-local.json').read_text(encoding='utf-8-sig'))
    checkpoint = Path(cfg['model_dir']) / 'checkpoints' / cfg['checkpoint']
    print('Loading local SDXL checkpoint; downloading configuration files only', flush=True)
    pipe = StableDiffusionXLPipeline.from_single_file(str(checkpoint), torch_dtype=torch.float16,
        config='stabilityai/stable-diffusion-xl-base-1.0')
    pipe.set_progress_bar_config(disable=True)
    # Use the complete local Carey photo set. Every caption explicitly anchors
    # the subject as a Black man with dark brown skin so the adapter cannot
    # express the requested identity; captions alone do not guarantee likeness.
    photo_dir = ROOT / 'training' / 'carey' / 'photos'
    crop_boxes = {
        '1-Photo-1.jpg': (0,.08,1,.92), '2-Photo-2.jpg': (0,.15,1,.90),
        '7-Photo-7.jpg': (0,.08,1,.83), '8-Photo-8.jpg': (0,.05,1,.80),
        '9-Photo-9.jpg': (0,.10,1,.85), '10-Photo-10.jpg': (0,.00,1,.92),
    }
    files = sorted([p for p in photo_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')], key=lambda p: p.name.lower())
    if len(files) < 10:
        raise RuntimeError(f'Expected at least 10 Carey photos, found {len(files)}')
    entries = []
    for source in files:
        box = crop_boxes.get(source.name, (0,.03,1,.97))
        image = ImageOps.exif_transpose(Image.open(source))
        full_body = image.height > image.width * 1.25
        framing = 'full-body reference' if full_body else 'portrait reference'
        caption = ('photo of byrdcarey man, Black man, dark brown skin, Black facial features, '
                   'natural afro-textured hair, short beard, ' + framing + ', realistic skin texture')
        entries.append((source.name, box, caption))
    captions = [row[2] for row in entries]
    # CPU prompt encoding avoids allocating both frozen text models on the GPU.
    print('Caching text embeddings on CPU', flush=True)
    with torch.no_grad():
        embeds, _, pooled, _ = pipe.encode_prompt(prompt=captions, device=torch.device('cpu'),
                                                num_images_per_prompt=1, do_classifier_free_guidance=False)
    embeds, pooled = embeds.cpu(), pooled.cpu()
    pipe.text_encoder = None; pipe.text_encoder_2 = None
    pipe.tokenizer = None; pipe.tokenizer_2 = None
    gc.collect()
    pipe.vae.to(device='cuda', dtype=torch.float32)
    cache = []
    for index, (name, box, caption) in enumerate(entries):
        source = ROOT / 'training' / 'carey' / 'photos' / name
        image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
        w,h = image.size
        image = image.crop(tuple(round(v * (w if i % 2 == 0 else h)) for i,v in enumerate(box)))
        image = ImageOps.fit(image, (args.resolution,args.resolution), method=Image.Resampling.LANCZOS)
        for flip in (False,True):
            variant = ImageOps.mirror(image) if flip else image
            pixels = torch.from_numpy(np.asarray(variant).copy()).permute(2,0,1).unsqueeze(0).float()/127.5-1
            with torch.no_grad():
                latent = pipe.vae.encode(pixels.to('cuda')).latent_dist.sample()*pipe.vae.config.scaling_factor
            cache.append((latent.cpu().half(),embeds[index:index+1].half(),pooled[index:index+1].half()))
        print('Cached '+name,flush=True)
    pipe.vae.to('cpu'); pipe.vae=None
    unet = pipe.unet; pipe.unet = None
    scheduler = DDPMScheduler.from_config(pipe.scheduler.config)
    del pipe; gc.collect(); torch.cuda.empty_cache()
    unet.requires_grad_(False)
    unet.add_adapter(LoraConfig(r=8,lora_alpha=8,init_lora_weights='gaussian',
        target_modules=['to_q','to_k','to_v','to_out.0']))
    for p in unet.parameters():
        if p.requires_grad: p.data=p.data.float()
    unet.to('cuda'); unet.train(); unet.enable_gradient_checkpointing()
    trainable=[p for p in unet.parameters() if p.requires_grad]
    optimizer=torch.optim.AdamW(trainable,lr=1e-4,betas=(.9,.999),weight_decay=.01,eps=1e-8)
    scaler=torch.amp.GradScaler('cuda')
    time_ids=torch.tensor([[args.resolution,args.resolution,0,0,args.resolution,args.resolution]],device='cuda',dtype=torch.float16)
    loss_log=[]; started=time.monotonic()
    def save(step):
        weights=convert_state_dict_to_diffusers(get_peft_model_state_dict(unet))
        weights={'unet.'+k:v.detach().cpu().float() for k,v in weights.items()}
        kohya=convert_state_dict_to_kohya(convert_all_state_dict_to_peft(weights))
        path=out/f'carey_sdxl_v1_step{step}.safetensors'
        save_file(kohya,str(path),metadata={'ss_base_model_version':'sdxl_base_v1-0',
            'ss_network_module':'networks.lora','ss_network_dim':'8','ss_network_alpha':'8',
            'byrdhouse_trigger':'byrdcarey man','byrdhouse_status':'experimental_needs_review'})
        print('Saved '+str(path),flush=True)
        return path
    for step in range(1,args.steps+1):
        latent,embedding,pool=random.choice(cache)
        latent,embedding,pool=[t.to('cuda') for t in (latent,embedding,pool)]
        noise=torch.randn_like(latent)
        timestep=torch.randint(0,scheduler.config.num_train_timesteps,(1,),device='cuda',dtype=torch.long)
        noisy=scheduler.add_noise(latent,noise,timestep)
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast('cuda',dtype=torch.float16):
            prediction=unet(noisy,timestep,encoder_hidden_states=embedding,
                added_cond_kwargs={'text_embeds':pool,'time_ids':time_ids},return_dict=False)[0]
            target=noise if scheduler.config.prediction_type=='epsilon' else scheduler.get_velocity(latent,noise,timestep)
            loss=F.mse_loss(prediction.float(),target.float())
        if not torch.isfinite(loss): raise RuntimeError('Non-finite training loss')
        scaler.scale(loss).backward(); scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(trainable,1.0)
        scaler.step(optimizer); scaler.update()
        loss_log.append(float(loss.detach()))
        if step==1 or step%10==0:
            elapsed=time.monotonic()-started
            status(state='training',step=step,steps=args.steps,seconds=round(elapsed,1),
                loss=loss_log[-1],gpu_peak_gib=round(torch.cuda.max_memory_allocated()/2**30,2))
            print(f'{step}/{args.steps} loss={loss_log[-1]:.5f} elapsed={elapsed:.1f}s',flush=True)
        if step%200==0: save(step)
    path=save(args.steps)
    manifest={'status':'experimental_needs_review','trigger':'byrdcarey man','base':str(checkpoint),
        'training_files':entries,'held_out':[],
        'steps':args.steps,'resolution':args.resolution,'rank':8,'learning_rate':1e-4,
        'loss':loss_log,'model':str(path),'seconds':time.monotonic()-started,
        'gpu':torch.cuda.get_device_name(0),'gpu_peak_gib':torch.cuda.max_memory_allocated()/2**30}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    status(state='trained_needs_review',model=str(path),steps=args.steps)

if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        status_path=ROOT/'training'/'carey'/'candidate-v1'/'status.json'
        status_path.parent.mkdir(parents=True,exist_ok=True)
        status_path.write_text(json.dumps({'state':'failed','error':str(exc)},indent=2),encoding='utf-8')
        raise
