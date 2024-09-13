from __future__ import annotations


from loguru import logger
from captum.attr import NoiseTunnel as CaptumNoiseTunnel

from meteors import HSI
from meteors.attr import HSIAttributes, Explainer


class NoiseTunnel(Explainer):
    def __init__(self, attribution_method: Explainer):
        super().__init__(attribution_method)
        if not isinstance(attribution_method, Explainer):
            raise TypeError(f"Expected Explainer as attribution_method, but got {type(attribution_method)}")
        if not attribution_method._attribution_method:
            raise ValueError("Attribution method is not initialized")
        self._attribution_method = CaptumNoiseTunnel(attribution_method._attribution_method)

    def attribute(
        self,
        hsi: HSI,
        target: int | None = None,
        nt_type="smoothgrad",
        nt_samples=5,
        nt_samples_batch_size=None,
        stdevs=1.0,
        draw_baseline_from_distrib=False,
    ) -> HSIAttributes:
        if self._attribution_method is None:
            raise ValueError("Noise Tunnel explainer is not initialized")
        if self.chained_explainer is None:
            raise ValueError(
                f"The attribution method {self.chained_explainer.__class__.__name__} is not properly initialized"
            )

        logger.debug("Applying Noise Tunnel on the image")

        noise_tunnel_attributes = self._attribution_method.attribute(
            hsi.get_image().unsqueeze(0),
            target=target,
            nt_type=nt_type,
            nt_samples=nt_samples,
            nt_samples_batch_size=nt_samples_batch_size,
            stdevs=stdevs,
            draw_baseline_from_distrib=draw_baseline_from_distrib,
        )

        attributes = HSIAttributes(
            hsi=hsi, attributes=noise_tunnel_attributes.squeeze(0), attribution_method=self.get_name()
        )

        return attributes
