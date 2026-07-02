"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.

Developer UI debug overlay (bottom bar), adapted for the BYD Tang DM
sunnypilot 0.10.1 build. Shows live values useful for lateral/longitudinal
debugging without needing an SSH session.

Controlled by the "DevUIInfo" param via ui_state.developer_ui:
  0 = OFF, 1 = BOTTOM bar, 2 = RIGHT column, 3 = BOTH
"""
from enum import IntEnum
from dataclasses import dataclass

import pyray as rl
from openpilot.common.constants import CV
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.application import gui_app, FontWeight
from openpilot.system.ui.lib.text_measure import measure_text_cached
from openpilot.system.ui.widgets import Widget

WHITE = rl.WHITE
GREEN = rl.Color(0, 245, 0, 255)
ORANGE = rl.Color(255, 188, 0, 255)
RED = rl.RED
GREY = rl.Color(145, 155, 149, 255)


class DeveloperUiState(IntEnum):
  OFF = 0
  BOTTOM = 1
  RIGHT = 2
  BOTH = 3


@dataclass
class UiElement:
  label: str
  value: str
  unit: str
  color: rl.Color = WHITE


def _lead(sm):
  lead = sm['radarState'].leadOne
  return lead.status, lead.dRel, lead.vRel


def _lead_color_dist(d_rel: float) -> rl.Color:
  if d_rel < 5:
    return RED
  if d_rel < 15:
    return ORANGE
  return WHITE


def _lat_active(sm) -> bool:
  try:
    return bool(sm['selfdriveStateSP'].mads.active)
  except Exception:
    return bool(sm['selfdriveState'].active)


def _collect_elements(sm, is_metric: bool) -> list[UiElement]:
  cs = sm['carState']
  controls = sm['controlsState']
  spd_conv = CV.MS_TO_KPH if is_metric else CV.MS_TO_MPH
  spd_unit = "km/h" if is_metric else "mph"

  lead_status, d_rel, v_rel = _lead(sm)
  lat_active = _lat_active(sm)
  steer_override = cs.steeringPressed

  elements: list[UiElement] = []

  # Lead relative distance
  elements.append(UiElement(
    "REL DIST",
    f"{d_rel:.0f}" if lead_status else "-",
    "m",
    _lead_color_dist(d_rel) if lead_status else WHITE,
  ))

  # Lead relative speed
  rel_color = WHITE
  if lead_status:
    if v_rel < -4.4704:
      rel_color = RED
    elif v_rel < 0:
      rel_color = ORANGE
  elements.append(UiElement(
    "REL SPEED",
    f"{v_rel * spd_conv:.0f}" if lead_status else "-",
    spd_unit,
    rel_color,
  ))

  # Real steering angle
  angle = cs.steeringAngleDeg
  angle_color = WHITE
  if lat_active:
    angle_color = GREY if steer_override else GREEN
  if abs(angle) > 180:
    angle_color = RED
  elif abs(angle) > 90:
    angle_color = ORANGE
  elements.append(UiElement("STEER", f"{angle:.1f}", "deg", angle_color))

  # EPS measured torque (native CAN units) - key BYD debug signal
  elements.append(UiElement("EPS TQ", f"{cs.steeringTorqueEps:.0f}", "", WHITE))

  # Driver steering torque (native CAN units) - 用于标定 hands-on 阈值。
  # 颜色: 越过 steeringPressed 阈值(=EPS握持标准, 边框会变灰)时显示灰色, 否则绿色,
  # 让标定时一眼看出"当前握持力是否已被判定为手在盘上"。
  drv_tq = cs.steeringTorque
  drv_color = GREY if steer_override else GREEN
  elements.append(UiElement("DRV TQ", f"{drv_tq:.0f}", "", drv_color))

  # Longitudinal acceleration
  elements.append(UiElement("A EGO", f"{cs.aEgo:.2f}", "m/s2", WHITE))

  return elements


class DeveloperUiRenderer(Widget):
  def __init__(self):
    super().__init__()
    self._font_bold: rl.Font = gui_app.font(FontWeight.BOLD)
    self._mode = DeveloperUiState.OFF

  def _update_state(self) -> None:
    self._mode = DeveloperUiState(ui_state.developer_ui) if ui_state.developer_ui in \
      (0, 1, 2, 3) else DeveloperUiState.OFF

  def _render(self, rect: rl.Rectangle) -> None:
    if self._mode == DeveloperUiState.OFF:
      return

    sm = ui_state.sm
    if sm.recv_frame["carState"] < ui_state.started_frame:
      return

    if self._mode in (DeveloperUiState.BOTTOM, DeveloperUiState.BOTH):
      self._draw_bottom(rect)
    if self._mode in (DeveloperUiState.RIGHT, DeveloperUiState.BOTH):
      self._draw_right(rect)

  def _draw_bottom(self, rect: rl.Rectangle) -> None:
    sm = ui_state.sm
    elements = _collect_elements(sm, ui_state.is_metric)
    if not elements:
      return

    bar_height = 61
    y = int(rect.y + rect.height - bar_height)
    rl.draw_rectangle(int(rect.x), y, int(rect.width), bar_height, rl.Color(0, 0, 0, 120))

    font_size = 34
    widths = []
    for e in elements:
      w = measure_text_cached(self._font_bold, f"{e.label} {e.value} {e.unit}".strip(), font_size).x
      widths.append(w)

    total = sum(widths)
    gaps = len(elements) + 1
    gap = (rect.width - total) / gaps
    center_y = y + bar_height // 2 - font_size // 2
    cur_x = rect.x + gap

    for i, e in enumerate(elements):
      self._draw_inline(cur_x, center_y, e, font_size)
      cur_x += widths[i] + gap

  def _draw_inline(self, x: float, y: float, e: UiElement, font_size: int) -> None:
    label_txt = f"{e.label} "
    val_txt = e.value
    unit_txt = f" {e.unit}" if e.unit else ""
    lw = measure_text_cached(self._font_bold, label_txt, font_size).x
    vw = measure_text_cached(self._font_bold, val_txt, font_size).x
    rl.draw_text_ex(self._font_bold, label_txt, rl.Vector2(x, y), font_size, 0, WHITE)
    rl.draw_text_ex(self._font_bold, val_txt, rl.Vector2(x + lw, y), font_size, 0, e.color)
    if unit_txt:
      rl.draw_text_ex(self._font_bold, unit_txt, rl.Vector2(x + lw + vw, y), font_size, 0, WHITE)

  def _draw_right(self, rect: rl.Rectangle) -> None:
    sm = ui_state.sm
    elements = _collect_elements(sm, ui_state.is_metric)
    if not elements:
      return

    container_width = 184
    border = 20
    x = int(rect.x + rect.width - container_width - border * 2)
    y = int(rect.y + border * 1.5) + 230
    label_size = 28
    value_size = 56

    for e in elements:
      lw = measure_text_cached(self._font_bold, e.label, label_size).x
      rl.draw_text_ex(self._font_bold, e.label, rl.Vector2(x + (container_width - lw) / 2, y), label_size, 0, WHITE)
      y += 45
      disp = f"{e.value}{(' ' + e.unit) if e.unit else ''}"
      vw = measure_text_cached(self._font_bold, disp, value_size).x
      rl.draw_text_ex(self._font_bold, disp, rl.Vector2(x + (container_width - vw) / 2, y), value_size, 0, e.color)
      y += 85
