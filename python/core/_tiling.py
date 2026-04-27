"""
Tiled diffusion utilities — MultiDiffusion weighted-average tile blending.

Algorithm reference
-------------------
    Bar-Tal et al., "MultiDiffusion: Fusing Diffusion Paths for
    Controlled Image Generation", ICML 2023.
    https://multidiffusion.github.io/
    (No source code was copied; this is a clean-room implementation using
    only standard PyTorch tensor operations derived from the paper's
    equations.)

License
-------
This file is original work and may be released under MIT or any other
commercial-friendly licence.  All dependencies (torch, diffusers scheduler
objects) are Apache 2.0 / BSD — no GPL or AGPL code is used.

Design
------
The UNet has a fixed receptive field (typically 512 × 512 image pixels =
64 × 64 latent pixels for SD 1.x).  Passing a larger latent directly
produces artefacts because the positional encoding was never trained beyond
that size.  Tiled diffusion solves this by:

  1. Splitting the latent into overlapping tiles of ``tile_size × tile_size``.
  2. Running the UNet independently on each tile to get per-tile noise
     predictions.
  3. For every pixel in the full latent, taking the *weighted average* of all
     tile predictions that covered it — the weight for a tile pixel is given
     by a Gaussian window that is 1.0 at the tile centre and tapers to ~0 at
     the edges.
  4. Using that merged noise prediction for the normal scheduler step.

Because the weight function peaks at the centre and decays toward edges,
pixels near tile seams are dominated by the tiles whose centres are closest,
preventing hard borders.
"""

from __future__ import annotations

from typing import Any, Generator


# ── Tile iterator ─────────────────────────────────────────────────────────────

def iter_tiles(
    h: int,
    w: int,
    tile_size: int,
    tile_overlap: int,
) -> Generator[tuple[int, int, int, int], None, None]:
    """
    Yield ``(row_start, row_end, col_start, col_end)`` covering ``(h, w)``.

    Tiles are placed on a stride = ``tile_size - tile_overlap`` grid.
    The final tile in each dimension is always snapped to the far edge so
    every pixel in the latent is covered by at least one tile, even when the
    latent dimensions are not exact multiples of the stride.

    Parameters
    ----------
    h, w         : full latent height and width (in latent pixels)
    tile_size    : side length of each tile (same for H and W)
    tile_overlap : number of latent pixels shared between adjacent tiles
    """
    stride = max(1, tile_size - tile_overlap)

    def _starts(dim: int) -> list[int]:
        # Regular grid positions
        pts = list(range(0, max(1, dim - tile_size + 1), stride))
        # Ensure the last tile always reaches the far edge
        edge = max(0, dim - tile_size)
        if not pts or pts[-1] != edge:
            pts.append(edge)
        return pts

    for rs in _starts(h):
        re = min(rs + tile_size, h)
        for cs in _starts(w):
            ce = min(cs + tile_size, w)
            yield rs, re, cs, ce


# ── Gaussian weight window ────────────────────────────────────────────────────

def make_tile_weights(
    tile_h: int,
    tile_w: int,
    dtype: Any,
    device: Any,
    torch: Any,
) -> Any:
    """
    Return a ``(1, 1, tile_h, tile_w)`` Gaussian weight tensor.

    The window is 1.0 at the centre and decays toward the edges with
    ``sigma = size / 6``, so the outermost ring is at roughly 1 % of peak.
    The outer product of two 1-D Gaussian vectors gives a 2-D separable
    Gaussian — mathematically equivalent to a full 2-D Gaussian with
    circular symmetry in the limit of large tile sizes.
    """

    def _gauss_1d(n: int) -> Any:
        sigma = n / 6.0
        x = torch.arange(n, dtype=torch.float32) - (n - 1) / 2.0
        return torch.exp(-0.5 * (x / sigma) ** 2)

    wy   = _gauss_1d(tile_h)          # (tile_h,)
    wx   = _gauss_1d(tile_w)          # (tile_w,)
    grid = wy[:, None] * wx[None, :]  # (tile_h, tile_w)  outer product
    return grid[None, None].to(dtype=dtype, device=device)  # (1, 1, H, W)


# ── Core tiled UNet forward ───────────────────────────────────────────────────

def tiled_noise_pred(
    unet: Any,
    latents: Any,
    t: Any,
    text_embeddings: Any,
    sched_obj: Any,
    cfg: float,
    tile_size: int,
    tile_overlap: int,
    torch: Any,
) -> Any:
    """
    MultiDiffusion tiled UNet forward pass.

    For each tile that covers ``latents``:
      1. Extract the tile sub-tensor.
      2. Classifier-free guidance: concatenate unconditional + conditional
         along the batch dimension and run the UNet once.
      3. Compute the CFG-merged noise prediction for the tile.
      4. Accumulate into full-resolution weighted sum buffers.

    After all tiles are processed, divide the accumulated noise sum by the
    accumulated weight sum.  Because every spatial position is covered by at
    least one tile, ``weight_sum > 0`` everywhere and the division is safe.

    The ``torch`` module is received as a parameter so this file has zero
    module-level hard imports (matching the deferred-import pattern used by
    the rest of the backend layer).

    Parameters
    ----------
    unet            : UNet2DConditionModel (or any callable with the same
                      signature)
    latents         : (B, C, H, W) latent tensor
    t               : current diffusion timestep scalar tensor
    text_embeddings : (2*B, seq, dim) — [uncond; cond] concatenated
    sched_obj       : diffusers scheduler instance (must have
                      ``.scale_model_input()``)
    cfg             : classifier-free guidance scale
    tile_size       : tile side in latent pixels
    tile_overlap    : overlap between adjacent tiles in latent pixels
    torch           : the torch module

    Returns
    -------
    noise_pred : (B, C, H, W) merged noise prediction
    """
    B, C, H, W = latents.shape

    noise_sum  = torch.zeros_like(latents)
    weight_sum = torch.zeros(B, 1, H, W, dtype=latents.dtype, device=latents.device)

    # Cast timestep to the latent dtype — required on Apple MPS where mixed
    # float16/float32 timestep arithmetic produces silent NaN.
    t_cast = t.to(dtype=latents.dtype) if hasattr(t, "to") else t

    for rs, re, cs, ce in iter_tiles(H, W, tile_size, tile_overlap):
        tile_h = re - rs
        tile_w = ce - cs

        # Extract tile
        tile_latent = latents[:, :, rs:re, cs:ce]

        # Classifier-free guidance: duplicate along batch for uncond + cond
        tile_input = torch.cat([tile_latent] * 2)
        tile_input = sched_obj.scale_model_input(tile_input, t)

        with torch.no_grad():
            tile_noise = unet(
                tile_input,
                t_cast,
                encoder_hidden_states=text_embeddings,
            ).sample

        # Split unconditional / conditional predictions and apply CFG
        noise_uncond, noise_text = tile_noise.chunk(2)
        tile_noise_pred = noise_uncond + cfg * (noise_text - noise_uncond)

        # Gaussian weights for this tile
        w = make_tile_weights(
            tile_h, tile_w,
            dtype=latents.dtype,
            device=latents.device,
            torch=torch,
        )

        noise_sum [:, :, rs:re, cs:ce] += tile_noise_pred * w
        weight_sum[:, :, rs:re, cs:ce] += w

    # Normalise: every pixel has weight_sum > 0.
    return noise_sum / weight_sum
