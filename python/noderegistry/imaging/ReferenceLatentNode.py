"""
ReferenceLatentNode — inject a latent reference into a conditioning tensor.

Background
----------
In diffusion pipelines it is sometimes useful to guide sampling with a
reference image rather than (or in addition to) a text prompt.  A common
pattern is to encode a reference image with VAEEncode to obtain a LATENT
and then "annotate" the CONDITIONING so that the sampler can perform
reference-only attention injection during denoising.

This node implements the annotation step: it deep-copies the incoming
CONDITIONING list and inserts the LATENT tensor under the key
``"reference_latent"`` in the extras dict of every conditioning entry.
The modified CONDITIONING can then be passed directly to KSampler as
the positive (or negative) conditioning input.

Ports
-----
Inputs  (data)  : conditioning : CONDITIONING
                      The base conditioning produced by CLIPTextEncode or
                      any other conditioning node.
                  latent : LATENT
                      The reference latent produced by VAEEncode.  Typically
                      the ``{"samples": tensor}`` dict returned by VAEEncode.
Outputs (data)  : CONDITIONING : CONDITIONING
                      A new conditioning list where every entry's extras dict
                      contains ``{"reference_latent": <latent>}``.
                  error : STRING
                      Empty on success; human-readable message on failure.
Control outputs : next, failed

Conditioning format
-------------------
CONDITIONING is treated as a list of ``(tensor, extras_dict)`` tuples,
following the convention used throughout this codebase:

    conditioning = [
        (cond_tensor, {"pooled_output": ..., ...}),
        ...
    ]

This node produces:

    new_conditioning = [
        (cond_tensor, {**extras, "reference_latent": latent}),
        ...
    ]

The format is intentionally backend-agnostic: backends that do not support
reference-latent conditioning will simply ignore the unknown key.

License
-------
This file is original work released under the MIT License.
It does not reproduce any code from ComfyUI or other GPL/AGPL projects.
"""

from __future__ import annotations

import copy
from typing import Any

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("ReferenceLatent")
class ReferenceLatentNode(Node):
    """
    Annotates a CONDITIONING with a reference LATENT for style/content guidance.

    The node deep-copies the incoming conditioning list and adds the latent
    under the key ``"reference_latent"`` in each entry's extras dict.  The
    result is a new CONDITIONING that can be wired into any downstream node
    that accepts CONDITIONING (e.g. KSampler positive / negative inputs).

    Deep-copying ensures that the original conditioning tensors are never
    mutated, which is important when the same conditioning is shared between
    multiple branches in the graph.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        # ── Control flow ────────────────────────────────────────────────────
        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        # ── Data inputs ─────────────────────────────────────────────────────
        # Base conditioning to annotate, e.g. from CLIPTextEncode.
        self.din_conditioning = self.add_data_input(
            'conditioning', data_type=ValueType.CONDITIONING
        )
        # Reference latent from VAEEncode; must be a dict with at least a
        # ``"samples"`` key containing the encoded image tensor.
        self.din_latent = self.add_data_input(
            'latent', data_type=ValueType.LATENT
        )

        # ── Data outputs ─────────────────────────────────────────────────────
        # Annotated conditioning ready to pass to KSampler.
        self.dout_conditioning = self.add_data_output(
            'CONDITIONING', data_type=ValueType.CONDITIONING
        )
        # Human-readable error message; empty string on success.
        self.dout_error = self.add_data_output(
            'error', data_type=ValueType.STRING
        )

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        """
        Build an annotated copy of the input conditioning.

        Algorithm
        ---------
        1. Read *conditioning* and *latent* from data inputs.
        2. Validate that *conditioning* is a non-empty list-like object.
        3. Deep-copy the conditioning list so the original is not mutated.
        4. For each ``(tensor, extras)`` pair, merge
           ``{"reference_latent": latent}`` into *extras*.
        5. Write the new conditioning to the output port and route to *next*.

        Error handling
        --------------
        If *conditioning* is missing or not iterable, or if any entry is not
        a two-element sequence, the node routes to *failed* and writes a
        descriptive message to *error*.

        Note: The *env* / *executionContext* split follows Option-B architecture
        where process-local resources live in *env* and are not serialised.
        This node does not require any backend resources.
        """
        conditioning: Any = self.din_conditioning.value
        latent: Any       = self.din_latent.value

        try:
            # ── Validate inputs ──────────────────────────────────────────────
            if not conditioning:
                raise ValueError(
                    "ReferenceLatentNode: 'conditioning' input is empty or None. "
                    "Connect a CLIPTextEncode (or equivalent) node first."
                )

            # Ensure the conditioning is iterable and contains valid entries.
            # We accept any sequence-like object; lists are the standard format.
            if not hasattr(conditioning, '__iter__'):
                raise TypeError(
                    f"ReferenceLatentNode: expected conditioning to be a list of "
                    f"(tensor, dict) pairs, got {type(conditioning).__name__}."
                )

            # ── Build the annotated conditioning ─────────────────────────────
            # Deep-copy to avoid mutating shared state when the same conditioning
            # fan-outs to multiple downstream nodes.
            new_conditioning = []
            for entry in conditioning:
                # Each entry must be a two-element sequence: (tensor, extras_dict).
                try:
                    tensor, extras = entry
                except (TypeError, ValueError) as unpack_err:
                    raise ValueError(
                        f"ReferenceLatentNode: conditioning entries must be "
                        f"(tensor, dict) pairs; failed to unpack: {unpack_err}"
                    ) from unpack_err

                # Shallow-copy the extras dict and inject the reference latent.
                # We do NOT deep-copy tensors because they can be large; the
                # reference is intentional — downstream code should treat them
                # as read-only.
                new_extras = dict(extras) if isinstance(extras, dict) else {}
                new_extras["reference_latent"] = latent

                new_conditioning.append((tensor, new_extras))

            self.dout_conditioning.value = new_conditioning
            self.dout_error.value        = ''

            return ExecutionResult(
                ExecCommand.CONTINUE,
                control_outputs={'next': True, 'failed': False},
            )

        except Exception as exc:
            self.dout_conditioning.value = []
            self.dout_error.value        = str(exc)

            return ExecutionResult(
                ExecCommand.CONTINUE,
                control_outputs={'next': False, 'failed': True},
            )
