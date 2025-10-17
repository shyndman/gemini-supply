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
import base64
import sys


def display_image_kitty(png_bytes: bytes, max_width: int | None = None) -> None:
  """Display a PNG image in the terminal using the Kitty graphics protocol.

  Args:
      png_bytes: The PNG image data as bytes
      max_width: Optional maximum width in pixels for the displayed image
  """
  # Encode the PNG data as base64
  encoded = base64.b64encode(png_bytes).decode("ascii")

  # Build the control data for the Kitty graphics protocol
  # a=T: transmit and display
  # f=100: PNG format
  # t=d: direct transmission (no temp file)
  control_parts = ["a=T", "f=100", "t=d"]

  if max_width is not None:
    # Set the width in pixels
    control_parts.append(f"w={max_width}")

  control_data = ",".join(control_parts)

  # The Kitty graphics protocol format:
  # ESC _G<control>;<payload>ESC \
  # where ESC is \x1b
  escape_sequence = f"\x1b_G{control_data};{encoded}\x1b\\"

  # Write directly to stdout
  sys.stdout.write(escape_sequence)
  sys.stdout.write("\n")
  sys.stdout.flush()
