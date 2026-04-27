"""
VAEDecodeNode — decode a latent tensor to a pixel-space IMAGE.

Ports
-----
Inputs  (data)  : VAE : VAE, samples : LATENT
Outputs (data)  : IMAGE : IMAGE
Control outputs : next, failed
"""

from __future__ import annotations

import asyncio
from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType
from ...server.trace.image_preview import to_data_url


@Node.register("VAEDecode")
class VAEDecodeNode(Node):
    """
    Decodes a LATENT tensor into a full-resolution IMAGE using the supplied
    VAE handle.  Typically wired immediately after KSampler.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        self.din_vae     = self.add_data_input('VAE',     data_type=ValueType.VAE)
        self.din_samples = self.add_data_input('samples', data_type=ValueType.LATENT)

        self.dout_image  = self.add_data_output('IMAGE', data_type=ValueType.IMAGE)
        self.dout_error  = self.add_data_output('error', data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        vae_handle = self.din_vae.value
        latent     = self.din_samples.value or {}
        try:
            backend = env.backend if env is not None else executionContext.env.backend
            if executionContext is not None and hasattr(executionContext, "report_detail"):
                await executionContext.report_detail({"url": None})
            image   = await asyncio.to_thread(backend.decode_vae, vae_handle, latent)
            self.dout_image.value = image
            self.dout_error.value = ''
            if executionContext is not None and hasattr(executionContext, "report_detail"):
                await executionContext.report_detail({"url": to_data_url(image)})
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_image.value = None
            self.dout_error.value = str(exc)
            if executionContext is not None and hasattr(executionContext, "report_detail"):
                await executionContext.report_detail({"url": None})
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
