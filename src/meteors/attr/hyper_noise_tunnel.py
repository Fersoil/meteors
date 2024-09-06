from __future__ import annotations

from functools import partial
import inspect

from typing import Any, Union, Literal

from meteors.attr import Explainer, ImageAttributes
from meteors.attr.explainer import validate_and_transform_baseline
from meteors import Image

import torch
from torch import Tensor

from captum.attr._utils.attribution import GradientAttribution
from captum.attr import Attribution


from loguru import logger


def torch_random_choice(n: int, k: int, n_samples: int, device: torch.device) -> torch.Tensor:
    """Randomly selects `k` elements from the range [0, n) without replacement.

    Args:
        n (int): The range of the selection.
        k (int): The number of elements to select.
        n_samples (int): The number of samples to be drawn.
        device (torch.device): The device to which the tensor will be moved.
    Returns:
        torch.Tensor: A tensor of shape (n_samples,n) containing True for the selected elements and False for the rest. Each row contains k True values.
    """
    if k > n:
        raise ValueError(f"Cannot select {k} elements from the range [0, {n})")
    if k == n:
        return torch.ones((n_samples, n), device=device).bool()
    result = torch.zeros((n_samples, n), device=device).bool()
    for i in range(n_samples):
        result[i, torch.randperm(n)[:k]] = True
    return result


class BaseHyperNoiseTunnel(Attribution):
    def __init__(self, model: GradientAttribution):
        self.attribute_main = model.attribute
        sig = inspect.signature(self.attribute_main)
        if "abs" in sig.parameters:
            self.attribute_main = partial(self.attribute_main, abs=False)

    @staticmethod
    def perturb_input(
        input, baseline, n_samples: int = 1, perturbation_prob: float = 0.5, num_perturbed_bands: int | None = None
    ):
        """The perturbation function used in the hyper noise tunnel. It randomly selects a subset of the input bands
        that will be masked out and replaced with the baseline. The parameters `num_perturbed_bands` and
        `perturbation_prob` control the number of bands that will be perturbed (masked). If `num_perturbed_bands` is
        set, it will be used as the number of bands to perturb, which will be randomly selected. Otherwise, the number
        of bands will be drawn from a binomial distribution with `perturbation_prob` as the probability of success.

        Args:
            input (torch.Tensor): An input tensor to be perturbed. It should have the shape (C, H, W).
            baseline (torch.Tensor): A baseline tensor to replace the perturbed bands.
            n_samples (int): A number of samples to be drawn - number of perturbed inputs to be generated.
            perturbation_prob (float, optional): A probability that each band will be perturbed intependently. Defaults to 0.5.
            num_perturbed_bands (int | None, optional): A number of perturbed bands in the whole image. If set to None, the bands are perturbed with probability `perturbation_prob` each. Defaults to None.

        Returns:
            torch.Tensor: A perturbed tensor, which contains `n_samples` perturbed inputs.
        """
        if input.dim() != 3 and input.dim() != 4:
            raise ValueError("Input must be in the format (C, H, W) or (N, C, H, W)")

        # validate the baseline against the input
        if baseline.shape != input.shape:
            raise ValueError(f"Baseline shape {baseline.shape} does not match input shape {input.shape}")

        if n_samples < 1:
            raise ValueError("Number of perturbated samples to be generated must be greater than 0")

        if perturbation_prob < 0 or perturbation_prob > 1:
            raise ValueError("Perturbation probability must be in the range [0, 1]")

        # the perturbation
        perturbed_input = input.clone().unsqueeze(0)
        # repeat the perturbed_input on the first dimension n_samples times
        perturbed_input = perturbed_input.repeat_interleave(n_samples, dim=0)

        n_samples_x_channels_shape = (
            n_samples,
            input.shape[0],
        )  # shape of the tensor containing the perturbed channels for each sample

        channels_to_be_perturbed: torch.Tensor = torch.zeros(n_samples_x_channels_shape, device=input.device).bool()

        if num_perturbed_bands is None:
            channel_perturbation_probabilities = (
                torch.ones(n_samples_x_channels_shape, device=input.device) * perturbation_prob
            )
            channels_to_be_perturbed = torch.bernoulli(channel_perturbation_probabilities).bool()

        else:
            if num_perturbed_bands < 0 or num_perturbed_bands > input.shape[0]:
                raise ValueError(
                    f"Cannot perturb {num_perturbed_bands} bands in the input with {input.shape[0]} channels. The number of perturbed bands must be in the range [0, {input.shape[0]}]"
                )

            channels_to_be_perturbed = torch_random_choice(input.shape[0], num_perturbed_bands, n_samples, input.device)

        # now having chosen the perturbed channels, we can replace them with the baseline

        reshaped_baseline = baseline.unsqueeze(0).repeat_interleave(n_samples, dim=0)
        perturbed_input[channels_to_be_perturbed] = reshaped_baseline[channels_to_be_perturbed]

        perturbed_input.requires_grad_(True)

        return perturbed_input

    def attribute(
        self,
        inputs: Tensor,
        baselines: Union[Tensor, int, float],
        target: int | None = None,
        additional_forward_args: Any = None,
        n_samples: int = 5,
        steps_per_batch: int = 1,
        method: str = "smoothgrad",
        perturbation_prob: float = 0.5,
        num_perturbed_bands: int | None = None,
    ) -> Tensor:
        if method not in ["smoothgrad", "smoothgrad_sq", "vargrad"]:
            raise ValueError("Method must be one of 'smoothgrad', 'smoothgrad_sq', 'vargrad'")

        if inputs.dim() == 3:
            inputs = inputs.unsqueeze(0)
        elif inputs.dim() != 4:
            raise ValueError("Input must be in the format (N, C, H, W)")

        if isinstance(baselines, (int, float)):
            baselines = torch.zeros_like(inputs, device=inputs.device) + baselines
        elif baselines.dim() == 4:
            baselines = baselines.squeeze(0)
        elif baselines.dim() != 3:
            raise ValueError("Baselines must be in the format (C, H, W)")

        attributions = torch.empty((n_samples,) + inputs.shape, device=inputs.device)

        for batch in range(0, inputs.shape[0]):
            input = inputs[batch]
            perturbed_input = BaseHyperNoiseTunnel.perturb_input(
                input, baselines, n_samples, perturbation_prob, num_perturbed_bands
            )
            for i in range(0, n_samples, steps_per_batch):
                perturbed_batch = perturbed_input[i : i + steps_per_batch]
                attributions[i : i + steps_per_batch, batch] = self.attribute_main(
                    perturbed_batch, target=target, additional_forward_args=additional_forward_args
                )
            else:
                steps_left = n_samples % steps_per_batch
                if steps_left:
                    perturbed_batch = perturbed_input[-steps_left:]
                    attributions[-steps_left:, batch] = self.attribute_main(
                        perturbed_batch, target=target, additional_forward_args=additional_forward_args
                    )

        if method == "smoothgrad":
            return attributions.mean(dim=0)
        elif method == "smoothgrad_sq":
            return (attributions**2).mean(dim=0)
        else:
            return (attributions**2 - attributions.mean(dim=0) ** 2).mean(dim=0)


class HyperNoiseTunnel(Explainer):
    def __init__(self, attribution_method):
        super().__init__(attribution_method)
        if not isinstance(attribution_method, Explainer):
            raise TypeError(f"Expected Explainer as attribution_method, but got {type(attribution_method)}")
        if not attribution_method._attribution_method:
            raise ValueError("Attribution method is not initialized")
        self._attribution_method: Attribution = BaseHyperNoiseTunnel(attribution_method._attribution_method)

    def attribute(
        self,
        image: Image,
        baselines: int | float | Tensor | None = None,
        target: int | None = None,
        n_samples: int = 5,
        steps_per_batch: int = 1,
        perturbation_prob: float = 0.5,
        num_perturbed_bands: int | None = None,
        method: Literal["smoothgrad", "smoothgrad_sq", "vargrad"] = "smoothgrad",
    ):
        if image.orientation != ("C", "H", "W"):
            logger.warning(
                f"The image orientation is {image.orientation}. Switching the orientation to ('C', 'H', 'W')"
            )
            # image.change_orientation("CHW", inplace=True)
            raise ValueError(
                "The image orientation must be ('C', 'H', 'W'), the orientation change is not reviewed yet (pls come back Vladimir)"
            )

        baselines = validate_and_transform_baseline(baselines, image)

        attributes = self._attribution_method.attribute(
            image.image,
            baselines=baselines,
            target=target,
            n_samples=n_samples,
            steps_per_batch=steps_per_batch,
            method=method,
            perturbation_prob=perturbation_prob,
            num_perturbed_bands=num_perturbed_bands,
        )
        attributes = attributes.squeeze(0)

        image_attributes = ImageAttributes(image=image, attributes=attributes, attribution_method=self.get_name())
        return image_attributes
