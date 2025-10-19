# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import array
import base64
import fcntl
import struct
import sys
import termios
from typing import NamedTuple

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

_COLOR_TYPE_LABELS: dict[int, str] = {
  0: "grayscale",
  2: "truecolor",
  3: "indexed",
  4: "gray+alpha",
  6: "rgba",
}


class _PNGHeaderInfo(NamedTuple):
  valid: bool
  reason: str | None
  width: int | None
  height: int | None
  bit_depth: int | None
  color_type: int | None


class _TerminalWindowSize(NamedTuple):
  rows: int | None
  cols: int | None
  xpixel: int | None
  ypixel: int | None


def _parse_png_header(png_bytes: bytes) -> _PNGHeaderInfo:
  """Validate PNG bytes and extract IHDR fields.

  Returns (valid, reason, width, height, bit_depth, color_type).
  """
  if len(png_bytes) < 33:
    return _PNGHeaderInfo(False, "too short", None, None, None, None)
  if png_bytes[:8] != _PNG_SIGNATURE:
    return _PNGHeaderInfo(False, "bad signature", None, None, None, None)

  # First chunk should be IHDR: length(4) type(4) data(13) crc(4)
  length = int.from_bytes(png_bytes[8:12], "big")
  ctype = png_bytes[12:16]
  if ctype != b"IHDR" or length != 13:
    return _PNGHeaderInfo(False, "missing IHDR", None, None, None, None)
  if len(png_bytes) < 33:
    return _PNGHeaderInfo(False, "truncated IHDR", None, None, None, None)

  ihdr = png_bytes[16:29]
  width, height, bit_depth, color_type, _compression, _filter, _interlace = struct.unpack(
    ">IIBBBBB", ihdr
  )
  return _PNGHeaderInfo(True, None, width, height, bit_depth, color_type)


def _get_terminal_winsize() -> _TerminalWindowSize:
  """Return (rows, cols, xpixel, ypixel) for the current terminal, if available."""
  fds: list[int] = []
  try:
    fds.append(sys.stdout.fileno())
  except Exception:
    pass
  try:
    with open("/dev/tty", "rb") as tty:
      fds.append(tty.fileno())
  except Exception:
    pass

  for fd in fds:
    try:
      buf = array.array("H", [0, 0, 0, 0])
      try:
        fcntl.ioctl(fd, termios.TIOCGWINSZ, buf, True)  # type: ignore[misc]
      except TypeError:
        fcntl.ioctl(fd, termios.TIOCGWINSZ, buf)  # type: ignore[misc]
      rows, cols, xpix, ypix = buf.tolist()
      return _TerminalWindowSize(int(rows), int(cols), int(xpix), int(ypix))
    except Exception:
      continue
  return _TerminalWindowSize(None, None, None, None)


def display_image_kitty(png_bytes: bytes, max_width: int | None = None) -> None:
  """Display a PNG image in the terminal using the Kitty graphics protocol.

  Args:
      png_bytes: The PNG image data as bytes
      max_width: Optional maximum width in pixels for the displayed image
  """
  # Validate PNG header to surface the most useful failure details early
  valid, reason, width, height, bit_depth, color_type = _parse_png_header(png_bytes)
  ct_label = _COLOR_TYPE_LABELS.get(color_type or -1, "unknown")

  if not valid:
    reason_suffix = f"; reason={reason}" if reason else ""
    print(
      f"PNG invalid; skipping Kitty render (size={len(png_bytes)} bytes; "
      f"width={width} height={height} bit_depth={bit_depth} "
      f"color_type={color_type}({ct_label}){reason_suffix})"
    )
    return

  # Compute terminal-aware width cap, if needed
  apply_width: int | None = None
  if max_width is not None and max_width > 0:
    apply_width = max_width
  _rows, _cols, xpix, _ypix = _get_terminal_winsize()
  if xpix and width:
    margin = 10
    term_w = max(0, xpix - margin)
    apply_width = min(apply_width, term_w) if apply_width else term_w
  if apply_width is not None and width and apply_width >= width:
    apply_width = None

  # Encode the PNG data as base64
  encoded = base64.b64encode(png_bytes).decode("ascii")

  # Build the control data for the Kitty graphics protocol
  # a=T: transmit and display
  # f=100: PNG format
  # t=d: direct transmission (no temp file)
  control_parts = ["a=T", "f=100", "t=d"]

  if apply_width is not None:
    # Set the width in pixels
    control_parts.append(f"w={apply_width}")

  control_data = ",".join(control_parts)

  # Kitty requires chunked transmission for large payloads. Use 4096-byte chunks.
  chunk_size = 4096
  total = len(encoded)
  for i in range(0, total, chunk_size):
    chunk = encoded[i : i + chunk_size]
    more = 1 if (i + chunk_size) < total else 0
    # ESC _G<control>,m=<more>;<payload> ESC\
    sys.stdout.write(f"\x1b_G{control_data},m={more};{chunk}\x1b\\")
  # Final newline for cleanliness
  sys.stdout.write("\n")
  sys.stdout.flush()
