import random
from dataclasses import dataclass
from importlib.resources import files
from io import BytesIO

import cv2
import numpy as np
from cv2.typing import MatLike
from PIL import Image
from playwright.async_api import Position


@dataclass
class _Needle:
  image: Image.Image
  size: int
  mat: MatLike


def _load_needle(size: int) -> _Needle:
  needle_image = Image.open(
    BytesIO(files("generative_supply.auth").joinpath(f"needle_{size}.png").read_bytes())
  ).convert("RGB")
  needle_mat = cv2.cvtColor(np.array(needle_image), cv2.COLOR_RGB2BGR)
  return _Needle(image=needle_image, size=size, mat=needle_mat)


_NEEDLES = {
  24: _load_needle(24),
  60: _load_needle(60),
}


def find_interactive_element_click_location(screenshot_bytes: bytes) -> Position | None:
  screenshot_image = Image.open(BytesIO(screenshot_bytes))
  screenshot = cv2.cvtColor(np.array(screenshot_image), cv2.COLOR_RGB2BGR)

  for needle in _NEEDLES.values():
    result = cv2.matchTemplate(screenshot, needle.mat, cv2.TM_CCOEFF_NORMED)
    threshold = 0.8
    locations = np.where(result >= threshold)

    if len(locations[0]) > 0:
      return Position(
        x=int(locations[1][0])
        + (needle.size // 2)
        + random.randint(-needle.size // 3, needle.size // 3),
        y=int(locations[0][0])
        + (needle.size // 2)
        + random.randint(-needle.size // 3, needle.size // 3),
      )
  return None
