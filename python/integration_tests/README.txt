

NODEGRAPH_TEST_MODEL=/tmp/tiny-sd NODEGRAPH_TEST_DEVICE=mps NODEGRAPH_TEST_DTYPE=float32 NODEGRAPH_TEST_STEPS=2 python3 -m pytest python/integration_tests/test_imaging_pipeline.py -v --tb=short 2>&1



python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    'hf-internal-testing/tiny-stable-diffusion-pipe',
    local_dir='/Users/robertpringle/development/ai_models/tiny-sd',
    ignore_patterns=['*.msgpack', '*.h5', 'flax_model*', 'tf_model*', 'rust_model*']
)
"


NODEGRAPH_TEST_MODEL=/Users/robertpringle/development/ai_models/tiny-sd NODEGRAPH_TEST_DEVICE=mps NODEGRAPH_TEST_DTYPE=float32 NODEGRAPH_TEST_STEPS=2 python3 -m pytest python/integration_tests/test_imaging_pipeline.py -v --tb=short 2>&1


================================================================================
CONVERTING .bin WEIGHTS TO SAFETENSORS
================================================================================

WHY THIS IS REQUIRED
--------------------
CVE-2025-32434 is a deserialization vulnerability in Python's pickle format,
which is the format used by PyTorch's .bin weight files. Newer versions of
`transformers` (>= ~4.50) block torch.load() entirely unless torch >= 2.6,
even when weights_only=True is set, because the vulnerability exists in the
pickle parsing layer itself.

When HuggingFace downloads a model in "diffusers format", each component
(unet/, vae/, text_encoder/) may contain either:
  - diffusion_pytorch_model.bin / pytorch_model.bin  (pickle, unsafe)
  - diffusion_pytorch_model.safetensors / model.safetensors  (safe)

transformers/diffusers always prefer the .safetensors file if present.
If only .bin exists and transformers is new enough, loading will fail.

HOW TO CONVERT
--------------
Run this script once per model directory. It reads each .bin file using the
current torch (which is allowed since we control the environment) and writes
a .safetensors equivalent alongside it. After conversion, the originals can
be kept or deleted — transformers will use safetensors first.

python3 -c "
import torch
from safetensors.torch import save_file
import os

model_dir = '/Users/robertpringle/development/ai_models/tiny-sd'

# Map: source .bin -> destination .safetensors
# Adjust this list for other models — check which .bin files exist under
# unet/, vae/, text_encoder/, safety_checker/ etc.
conversions = [
    ('text_encoder/pytorch_model.bin',       'text_encoder/model.safetensors'),
    ('unet/diffusion_pytorch_model.bin',     'unet/diffusion_pytorch_model.safetensors'),
    ('vae/diffusion_pytorch_model.bin',      'vae/diffusion_pytorch_model.safetensors'),
]

for src, dst in conversions:
    src_path = os.path.join(model_dir, src)
    dst_path = os.path.join(model_dir, dst)
    if not os.path.exists(src_path):
        print(f'SKIP (not found): {src}')
        continue
    if os.path.exists(dst_path):
        print(f'Already exists: {dst}')
        continue
    print(f'Converting {src} ...', flush=True)
    state_dict = torch.load(src_path, weights_only=True, map_location='cpu')
    save_file(state_dict, dst_path)
    print(f'  -> {dst}')

print('Done.')
"

HOW TO AVOID THIS IN THE FUTURE
--------------------------------
1. Download models that already ship safetensors. The HuggingFace Hub search
   filter "Files: safetensors" or model cards that list model.safetensors
   indicate safe format. The `hf-internal-testing/tiny-stable-diffusion-pipe`
   repo now includes safetensors; if you re-download with snapshot_download it
   will include them automatically.

2. When snapshot_download is used, it creates symlinks into ~/.cache/. Do not
   move the downloaded directory with `mv` — this moves the dangling symlinks
   without the actual data. Use `cp -rL` instead to follow symlinks and copy
   real content:

     cp -rL /tmp/tiny-sd /Users/robertpringle/development/ai_models/tiny-sd

   Or re-run snapshot_download with the new local_dir directly.

3. Keep torch >= 2.6 and transformers current. torch 2.6 restores the ability
   to use weights_only=True safely. Once the venv is updated to torch >= 2.6,
   the .bin -> .safetensors conversion is no longer strictly required (though
   safetensors loads faster and uses less memory).

