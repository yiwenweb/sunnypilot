"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Bottom-center horizontal acceleration bar.
Shows whether the vehicle is accelerating (green, grows right) or
decelerating (red, grows left) based on carState.aEgo.
Ported/adapted for the BYD Tang DM sunnypilot 0.10.1 build.
"""
import pyray as rl

from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.widgets import Widget

# Full-scale acceleration in m/s^2 that maps to the full half-width of the bar.
ACCEL_FULL_SCALE = 2.5
# Smoothing factor (higher = smoother/slower). Value is a simple IIR divisor.
SMOOTH_DIVISOR = 5.0

BAR_WIDTH = 600      # total track width in px
BAR_HEIGHT = 20      # track thickness in px
BAR_MARGIN_BOTTOM = 60  # distance from the bottom edge of the content rect

TRACK_COLOR = rl.Color(255, 255, 255, 40)
CENTER_COLOR = rl.Color(255, 255, 255, 120)
ACCEL_COLOR = rl.Color(0, 245, 0, 220)
DECEL_COLOR = rl.Color(245, 0, 0, 220)


class AccelBar(Widget):
  def __init__(self):
    super().__init__()
    self._accel = 0.0

  def _update_state(self) -> None:
    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      self._accel = 0.0
      return
    target = sm['carState'].aEgo
    self._accel += (target - self._accel) / SMOOTH_DIVISOR

  def _render(self, rect: rl.Rectangle) -> None:
    if not ui_state.accel_bar:
      return

    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      return

    # Track geometry: centered horizontally, near the bottom of the content rect.
    track_x = rect.x + (rect.width - BAR_WIDTH) / 2.0
    track_y = rect.y + rect.height - BAR_MARGIN_BOTTOM - BAR_HEIGHT
    center_x = track_x + BAR_WIDTH / 2.0

    # Background track.
    rl.draw_rectangle_rounded(
      rl.Rectangle(track_x, track_y, BAR_WIDTH, BAR_HEIGHT), 0.5, 10, TRACK_COLOR
    )

    # Fill proportional to acceleration, clamped to +/- full scale.
    frac = max(-1.0, min(1.0, self._accel / ACCEL_FULL_SCALE))
    fill_len = abs(frac) * (BAR_WIDTH / 2.0)

    if fill_len > 1.0:
      if frac > 0:  # accelerating: grow to the right from center
        fill_rect = rl.Rectangle(center_x, track_y, fill_len, BAR_HEIGHT)
        color = ACCEL_COLOR
      else:         # decelerating: grow to the left from center
        fill_rect = rl.Rectangle(center_x - fill_len, track_y, fill_len, BAR_HEIGHT)
        color = DECEL_COLOR
      rl.draw_rectangle_rounded(fill_rect, 0.5, 10, color)

    # Center tick.
    rl.draw_rectangle(int(center_x - 2), int(track_y - 4), 4, BAR_HEIGHT + 8, CENTER_COLOR)
