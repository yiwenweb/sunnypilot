/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/offroad/settings/longitudinal_panel.h"

LongitudinalPanel::LongitudinalPanel(QWidget *parent) : QWidget(parent) {
  main_layout = new QStackedLayout(this);
  ListWidget *list = new ListWidget(this, false);

  cruisePanelScreen = new QWidget(this);
  QVBoxLayout *vlayout = new QVBoxLayout(cruisePanelScreen);
  vlayout->setContentsMargins(0, 0, 0, 0);

  cruisePanelScroller = new ScrollViewSP(list, this);
  vlayout->addWidget(cruisePanelScroller);

  customAccIncrement = new CustomAccIncrement("CustomAccIncrementsEnabled", tr("自定义 ACC 速度增量"), "", "", this);
  list->addItem(customAccIncrement);

  // SCC Vision toggle
  sccVisionToggle = new ParamControlSP(
    "SmartCruiseControlVision",
    tr("Smart Cruise Control - Vision"),
    tr("使用视觉路径预测来估算前方弯道的适当车速。"),
    "../assets/offroad/icon_speed_limit.png",
    this
  );
  list->addItem(sccVisionToggle);

  // SCC Map toggle
  sccMapToggle = new ParamControlSP(
    "SmartCruiseControlMap",
    tr("Smart Cruise Control - 地图"),
    tr("使用地图数据来估算前方弯道的适当车速。"),
    "../assets/offroad/icon_speed_limit.png",
    this
  );
  list->addItem(sccMapToggle);

  // Green Light Alert toggle
  greenLightAlertToggle = new ParamControlSP(
    "GreenLightAlert",
    tr("绿灯提醒"),
    tr("停车等红灯时，检测到绿灯亮起会发出提示音。"),
    "../assets/offroad/icon_speed_limit.png",
    this
  );
  list->addItem(greenLightAlertToggle);

  // Lead Depart Alert toggle
  leadDepartAlertToggle = new ParamControlSP(
    "LeadDepartAlert",
    tr("前车起步提醒"),
    tr("前方车辆起步离开时发出提示音，提醒您继续行驶。"),
    "../assets/offroad/icon_speed_limit.png",
    this
  );
  list->addItem(leadDepartAlertToggle);

  // Speed Limit Policy toggle
  speedLimitPolicyToggle = new ParamControlSP(
    "SpeedLimitPolicy",
    tr("限速策略"),
    tr("选择 SCC 对限速的处理方式：0=关闭，1=仅参考，2=跟随限速，3=智能匹配（默认）。"),
    "../assets/offroad/icon_speed_limit.png",
    this
  );
  list->addItem(speedLimitPolicyToggle);

  QObject::connect(uiState(), &UIState::offroadTransition, this, &LongitudinalPanel::refresh);

  main_layout->addWidget(cruisePanelScreen);
  main_layout->setCurrentWidget(cruisePanelScreen);
  refresh(offroad);
}

void LongitudinalPanel::showEvent(QShowEvent *event) {
  main_layout->setCurrentWidget(cruisePanelScreen);
  refresh(offroad);
}

void LongitudinalPanel::refresh(bool _offroad) {
  auto cp_bytes = params.get("CarParamsPersistent");
  if (!cp_bytes.empty()) {
    AlignedBuffer aligned_buf;
    capnp::FlatArrayMessageReader cmsg(aligned_buf.align(cp_bytes.data(), cp_bytes.size()));
    cereal::CarParams::Reader CP = cmsg.getRoot<cereal::CarParams>();

    has_longitudinal_control = hasLongitudinalControl(CP);
    is_pcm_cruise = CP.getPcmCruise();
  } else {
    has_longitudinal_control = false;
    is_pcm_cruise = false;
  }

  QString accEnabledDescription = tr("启用自定义短按/长按的巡航速度增减量。");
  QString accNoLongDescription = tr("此功能需启用 openpilot 纵向控制才能使用。");
  QString accPcmCruiseDisabledDescription = tr("由于车辆限制，此平台不支持该功能。");
  QString onroadOnlyDescription = tr("启动车辆以检查车辆兼容性。");

  if (offroad) {
    customAccIncrement->setDescription(onroadOnlyDescription);
    customAccIncrement->showDescription();
  } else {
    if (has_longitudinal_control) {
      if (is_pcm_cruise) {
        customAccIncrement->setDescription(accPcmCruiseDisabledDescription);
        customAccIncrement->showDescription();
      } else {
        customAccIncrement->setDescription(accEnabledDescription);
      }
    } else {
      params.remove("CustomAccIncrementsEnabled");
      customAccIncrement->toggleFlipped(false);
      customAccIncrement->setDescription(accNoLongDescription);
      customAccIncrement->showDescription();
    }
  }

  // enable toggle when long is available and is not PCM cruise
  customAccIncrement->setEnabled(has_longitudinal_control && !is_pcm_cruise && !offroad);
  customAccIncrement->refresh();

  sccVisionToggle->setEnabled(has_longitudinal_control && !offroad);
  sccMapToggle->setEnabled(has_longitudinal_control && !offroad);
  sccVisionToggle->refresh();
  sccMapToggle->refresh();
  greenLightAlertToggle->refresh();
  leadDepartAlertToggle->refresh();
  speedLimitPolicyToggle->refresh();

  offroad = _offroad;
}
