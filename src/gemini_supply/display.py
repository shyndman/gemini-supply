from __future__ import annotations

from io import BytesIO
from typing import Callable, Protocol, cast

from PIL import Image
import term_image.image as term_image_image


class _Drawable(Protocol):
  def draw(self) -> None: ...


_AutoImageFactory = Callable[[Image.Image], _Drawable]

_auto_image = cast(_AutoImageFactory, term_image_image.AutoImage)


def display_image_kitty(png_bytes: bytes) -> None:
  with Image.open(BytesIO(png_bytes)) as img:
    drawable = _auto_image(img)
    drawable.draw()
