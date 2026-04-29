# compiled_modal — NodeGraph → Modal.com

This directory contains Python files compiled from NodeGraph graphs that target
the [Modal](https://modal.com) serverless GPU platform.  They are the output of
a compilation pathway analogous to `compiled_json/` but with Modal-specific
wrapping instead of a plain `asyncio.run()` entrypoint.

---

## How `ksampler_demo.py` works

The file is a hand-compiled translation of `saves/kSamplerDemo.json`.  The
graph has seven nodes arranged in a linear sequence:

```
CheckpointLoader
  → CLIPTextEncode (positive)
  → CLIPTextEncode (negative)
  → EmptyLatentImage
  → KSampler
  → VAEDecode
  → SaveImage
```

Each node maps to a private Python function in the file.  These are not
classes — the ML handles (pipe, conditioning tensors, latent) flow from
function to function as plain return values, mirroring the data edges in the
graph.

| Graph node | Python function | Notes |
|---|---|---|
| `CheckpointLoader` | `_checkpoint_loader()` | Loads SD 1.5 from HuggingFace hub; cached on a `modal.Volume` so the 4 GB download only happens once |
| `CLIPTextEncode` ×2 | `_clip_text_encode()` | Called once for positive, once for negative prompt |
| `EmptyLatentImage` | `_empty_latent_image()` | Creates a zeroed latent; KSampler overwrites it with noise when `denoise=1.0` |
| `KSampler` | `_ksampler()` | Manual CFG denoising loop using the diffusers scheduler API; respects `sampler_name`, `scheduler_name`, `cfg`, `steps`, `seed`, `denoise` |
| `VAEDecode` | `_vae_decode()` | Returns a `PIL.Image` |
| `SaveImage` | `_save_image()` | Serialises the image to PNG bytes; the local entrypoint writes them to `./output/` |

The `@app.function()` decorator wraps a single `generate()` function that
calls all of the above in topological order.  This matches the scheduler's
concept of a flat `SequenceBlock`.

### Modal-specific wiring

```
modal.App("ksampler-demo")
    └── modal.Image   — debian_slim + pip_install(torch, diffusers, …)
    └── modal.Volume  — "ksampler-model-cache" mounted at /model-cache
    └── @app.function(gpu="A10G", timeout=600)
          └── generate() → bytes
    └── @app.local_entrypoint()
          └── main() — calls generate.remote(), writes PNG to ./output/
```

The `SaveImage` node's "output_dir" behaviour is split across the boundary:
inside the container the image is encoded to bytes; outside, the local
entrypoint writes the file.  This is the correct Modal pattern — containers
should not write to the caller's filesystem directly.

---

## How to run

### Prerequisites

```bash
pip install modal
modal setup          # authenticate once
```

### First-time: create the model cache volume

```bash
modal volume create ksampler-model-cache
```

This creates a persistent Volume that caches the ~4 GB SD 1.5 weights so
they are only downloaded from HuggingFace once.

### Run the graph

```bash
modal run python/compiled_modal/ksampler_demo.py
```

The generated PNG is saved to `./output/ksampler_demo.png`.

### Override parameters at the command line

Modal exposes `@app.local_entrypoint()` parameters as CLI flags.  The
`generate()` function signature is the graph's parameter set, so you can pass
any of them without editing the file:

```bash
# Change prompt and seed
modal run python/compiled_modal/ksampler_demo.py \
  --positive-prompt "a cyberpunk city at night, neon reflections" \
  --seed 99999 \
  --steps 20
```

### Run asynchronously (fire and forget)

```bash
modal run --detach python/compiled_modal/ksampler_demo.py
```

---

## Generalising to arbitrary graphs

The ksampler demo was hand-compiled as a prototype.  The full generalisation
path maps directly onto the existing compiler pipeline:

```
graph.json
  → [compiler3.deserialiser]   json_to_ir()     → IRGraph
  → [compiler2.scheduler]      Scheduler.build() → IRSchedule
  → [compiler_modal.emitter]   emit_modal()      → modal Python source
```

Only the final phase (emitter + templates) needs to be new.  The IR,
scheduler, and deserialiser are already output-format-agnostic.

### What a `compiler_modal` package needs

#### 1. `emitter.py` — header and wrapper changes

The emitter produces three sections that differ from `compiler3/emitter.py`:

| Section | compiler3 | compiler_modal |
|---|---|---|
| File header | `import asyncio, os` | `import modal` + `app = modal.App(name)` + `image = modal.Image…` |
| `run()` function | bare `async def run()` | `@app.function(image=image, …)\nasync def run()` |
| Entrypoint | `asyncio.run(run())` | `@app.local_entrypoint()\ndef main(): run.remote()` |

Everything in between — the preamble deduplication, loop block emission,
sequence block emission — is identical and can be imported directly from
`compiler3/emitter.py`.

#### 2. `templates.py` — one new registry

Each `NodeTemplate` in `compiler3/templates.py` emits code that uses the
`openai` SDK.  Modal graphs that use diffusion nodes need an equivalent
`ModalNodeTemplate` registry that emits `diffusers` calls instead.

For the imaging node types you already have, the mapping is:

| Node type | Emitted code |
|---|---|
| `CheckpointLoader` | `pipe = StableDiffusionPipeline.from_pretrained(ckpt_path, cache_dir=MODEL_CACHE_DIR, …).to("cuda")` |
| `CLIPTextEncode` | `cond = _clip_text_encode(pipe, text)` |
| `EmptyLatentImage` | `latent = _empty_latent_image(pipe, width, height, batch_size)` |
| `KSampler` | `latent = _ksampler(pipe, pos, neg, latent, seed, steps, cfg, …)` |
| `VAEDecode` | `image = _vae_decode(pipe, latent)` |
| `SaveImage` | `png_bytes = _save_image(image)` (return value of `run()`) |
| `LLMNode` / `ToolAgentStreamNode` | Reuse compiler3 templates verbatim — they target openai SDK which works inside Modal without change |

#### 3. `resources.py` — per-graph Modal resource declaration

This is the trickiest part.  The `@app.function()` decorator arguments depend
on the graph content:

- `gpu=` — required for any imaging node; not needed for pure LLM graphs
- `volumes=` — required whenever `CheckpointLoader` or `SaveImage` is
  present; the volume name should be configurable
- `secrets=` — required when any LLM node is present (`OPENAI_API_KEY`)
- `image=` — the pip_install list must be derived from the node types in the
  graph

A `NodeResourceRequirements` dataclass per node type, merged during IR
traversal, cleanly solves this:

```python
@dataclass
class ModalResources:
    gpu: str | None          = None
    pip_packages: list[str]  = field(default_factory=list)
    volumes: dict[str, str]  = field(default_factory=dict)   # mount_path → volume_name
    secrets: list[str]       = field(default_factory=list)   # Modal secret names

# Per-node defaults, merged at compile time:
_NODE_RESOURCES: dict[str, ModalResources] = {
    "CheckpointLoader":  ModalResources(gpu="A10G", pip_packages=["diffusers", "torch", …], volumes={MODEL_CACHE_DIR: "ksampler-model-cache"}),
    "LLMNode":           ModalResources(pip_packages=["openai"], secrets=["openai-secret"]),
    "ToolAgentStreamNode": ModalResources(pip_packages=["openai"], secrets=["openai-secret"]),
    …
}
```

---

## Architectural notes

### What the saves format adds over the compiler3 JSON format

`saves/kSamplerDemo.json` is the native UI save format — it is richer but more
verbose than `graphs/ksampler_demo.json` (the compiler3 canonical format).
The key differences:

| Field | compiler3 JSON | saves JSON |
|---|---|---|
| Port values | `inputs: { "text": "…" }` | Full port objects with `port_type`, `data_type`, `direction`, `value`, etc. |
| IDs | Short friendly IDs (`"node_task"`) | UUID-style IDs (`"87b68267d2d0…"`) |
| Nesting | Flat `nodes[]` array | Nested `root_network → graph → nodes` |
| Edges | Explicit `edges[]` array | Encoded in `incoming_connections` / `outgoing_connections` on each port |

To compile directly from a saves file you need a `saves_to_ir()` deserialiser
in addition to the existing `json_to_ir()`.  This is a separate converter —
the schema is different enough that bolting it onto `compiler3/deserialiser.py`
would create coupling between two distinct formats.  A separate
`compiler_modal/saves_deserialiser.py` is the right home for it.

### The `backend` abstraction is a compiler boundary

The imaging nodes (`CheckpointLoaderNode`, `KSamplerNode`, etc.) use
`env.backend` at runtime — they do not import `diffusers` directly.  This
indirection is intentional and useful: it means the node definitions are
backend-agnostic and could run against different diffusion engines.

For compiled output the backend abstraction disappears entirely.  The emitter
inlines the concrete `diffusers` calls directly, just as `compiler3` inlines
the concrete `openai` calls.  There is no `env.backend` in the output file.

### `SaveImage` return convention for serverless

In the local runtime, `SaveImageNode` writes to disk.  In Modal, disk writes
inside a container are not visible to the caller.  The correct pattern —
demonstrated in `ksampler_demo.py` — is:

- `@app.function()` returns the PNG as `bytes`
- `@app.local_entrypoint()` writes the file

This pattern generalises: any node that produces a file artifact should be
treated as a data output (returning `bytes`) when targeting Modal.  The
entrypoint decides what to do with it (write to disk, upload to S3, etc.).
For graphs that produce multiple artifacts, `generate()` should return a
`dict[str, bytes]`.

### Streaming output

Modal supports generator functions via `is_generator=True` and `.remote_gen()`.
If you want the step-by-step KSampler progress to stream back to the caller
rather than only printing inside the container, the function signature changes:

```python
@app.function(gpu="A10G", image=image, volumes={…}, is_generator=True)
def generate_stream(…):
    for step_num, total, partial_image_bytes in _ksampler_stream(…):
        yield {"step": step_num, "total": total, "preview": partial_image_bytes}

# local entrypoint:
for event in generate_stream.remote_gen():
    print(f"Step {event['step']} / {event['total']}")
```

The `KSamplerStepNode` in `noderegistry/imaging/` already captures the
per-step callback pattern (`step_callback`, `_on_step`) — the emitter could
translate this into a Modal generator naturally.

### Multi-node parallelism

Modal's `.map()` and `.starmap()` let you run many invocations in parallel
with no extra infrastructure.  Graphs that have independent branches (e.g.
running the same prompt with 8 different seeds) compile naturally to:

```python
results = list(generate.map([
    {"seed": 1000}, {"seed": 2000}, …
]))
```

The compiler would need to detect independent branches in the IRGraph and
emit a `map` call rather than sequential calls — this is a future optimisation,
not required for the initial port.

### Cold starts and model caching

The `modal.Volume` approach used in `ksampler_demo.py` is the right long-term
pattern.  An alternative for low-latency production use is
`modal.build()` / `@app.cls` with `@modal.enter()` to keep the loaded
pipeline in memory across invocations on the same container.  The compiled
output would look like:

```python
@app.cls(gpu="A10G", image=image, volumes={…})
class Pipeline:
    @modal.enter()
    def load(self):
        self.pipe = _checkpoint_loader(…)

    @modal.method()
    def generate(self, **kwargs) -> bytes:
        # uses self.pipe — already loaded, no cold-start cost
        …
```

This is the recommended shape for a production `compiler_modal` target.

### Suggested new files for full compiler support

```
python/
  compiler_modal/
    __init__.py          — compile_graph_modal(graph, …) → str  (public API)
    emitter.py           — Modal-specific header + wrapper, reuses compiler3 body emitters
    templates.py         — ModalNodeTemplate registry (imaging + LLM)
    resources.py         — ModalResources dataclass + per-node default table
    saves_deserialiser.py— saves JSON → IRGraph (parallel to compiler3/deserialiser.py)
  compiled_modal/
    ksampler_demo.py     — prototype (this file, hand-compiled)
    …                    — future auto-generated outputs live here
```

The four existing compiler phases (IR, extractor, scheduler, compiler3 emitter)
are all reusable without modification.  The entire new surface is the
`compiler_modal/` package — roughly 300–400 lines of new code, of which ~150
lines are the per-node template bodies.
