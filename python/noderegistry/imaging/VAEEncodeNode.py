"""
VAEEncodeNode — encode a pixel-space IMAGE into a LATENT tensor.

Useful for img2img workflows: feed a loaded or modified image back into
KSampler via the latent space.

Ports
-----
Inputs  (data)  : VAE : VAE, pixels : IMAGE
Outputs (data)  : LATENT : LATENT
Control outputs : next, failed
"""

from __future__ import annotations

from ...core.Node import Node
from ...core.Executor import ExecCommand, ExecutionResult
from ...core.NodePort import ValueType


@Node.register("VAEEncode")
class VAEEncodeNode(Node):
    """
    Encodes a pixel-space IMAGE into a LATENT tensor using the supplied
    VAE handle.  Use this to feed an existing image into the KSampler for
    img2img or inpainting pipelines.
    """

    def __init__(self, id: str, type: str, network_id: str = None, **kwargs):
        super().__init__(id, type, network_id=network_id, **kwargs)
        self.is_flow_control_node = True

        self.cin_exec    = self.add_control_input('exec')
        self.cout_next   = self.add_control_output('next')
        self.cout_failed = self.add_control_output('failed')

        self.din_vae    = self.add_data_input('VAE',    data_type=ValueType.VAE)
        self.din_pixels = self.add_data_input('pixels', data_type=ValueType.IMAGE)

        self.dout_latent = self.add_data_output('LATENT', data_type=ValueType.LATENT)
        self.dout_error  = self.add_data_output('error',  data_type=ValueType.STRING)

    async def compute(self, executionContext=None, env=None) -> ExecutionResult:
        # Option B: env carries process-local resources (diffusion backend, tensor store).
        # Option A alternative would embed backend inside NodeContext — rejected because
        # NodeContext is serialisable and must not hold non-serialisable ML objects.
        vae_handle = self.din_vae.value
        image      = self.din_pixels.value
        try:
            backend = env.backend if env is not None else executionContext.env.backend
            latent  = backend.encode_vae(vae_handle, image)
            self.dout_latent.value = latent
            self.dout_error.value  = ''
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': True, 'failed': False})
        except Exception as exc:
            self.dout_latent.value = {}
            self.dout_error.value  = str(exc)
            return ExecutionResult(ExecCommand.CONTINUE, control_outputs={'next': False, 'failed': True})
