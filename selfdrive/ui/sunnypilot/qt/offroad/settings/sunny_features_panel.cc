/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/offroad/settings/sunny_features_panel.h"

SunnyFeaturesPanel::SunnyFeaturesPanel(QWidget *parent) : QWidget(parent) {
  param_watcher = new ParamWatcher(this);
  connect(param_watcher, &ParamWatcher::paramChanged, [=](const QString &param_name, const QString &param_value) {
    paramsRefresh();
  });

  main_layout = new QStackedLayout(this);
  ListWidgetSP *list = new ListWidgetSP(this, false);

  sunnyFeaturesScreen = new QWidget(this);
  QVBoxLayout* vlayout = new QVBoxLayout(sunnyFeaturesScreen);
  vlayout->setContentsMargins(50, 20, 50, 20);

  std::vector<std::tuple<QString, QString, QString, QString, bool> > toggle_defs{
    {
      "AccelBar",
      tr("加速度指示条"),
      tr("在屏幕左侧显示 RocketFuel 风格加速度竖条。绿色向上表示加速，红色向下表示减速。移植自 sunnypilot 2026 RocketFuel 功能。"),
      "../assets/offroad/icon_monitoring.png",
      false,
    },
    {
      "TurnSignal",
      tr("转向灯指示箭头"),
      tr("在屏幕左右两侧显示转向灯动态箭头图标。开启左/右转向灯时对应侧显示绿色动画箭头。"),
      "../assets/offroad/icon_monitoring.png",
      false,
    },
    {
      "SpeedLimit",
      tr("限速标志"),
      tr("在屏幕右上角显示当前道路的限速标志（维也纳风格圆形标识）。如果前方有限速变化，会显示前方限速提示。"),
      "../assets/offroad/icon_monitoring.png",
      false,
    },
    {
      "RoadName",
      tr("道路名称"),
      tr("在屏幕顶部居中显示当前行驶的道路名称（来自 OSM 地图数据）。"),
      "../assets/offroad/icon_monitoring.png",
      false,
    },
    {
      "SteeringArc",
      tr("转向弧度指示"),
      tr("在屏幕底部居中显示方向盘转向弧度。绿色表示横向控制激活，灰色表示手动操控。"),
      "../assets/offroad/icon_monitoring.png",
      false,
    },
  };

  for (auto &[param, title, desc, icon, needs_restart] : toggle_defs) {
    auto toggle = new ParamControlSP(param, title, desc, icon, this);

    bool locked = params.getBool((param + "Lock").toStdString());
    toggle->setEnabled(!locked);

    if (needs_restart && !locked) {
      toggle->setDescription(toggle->getDescription() + tr(" Changing this setting will restart openpilot if the car is powered on."));

      QObject::connect(uiState(), &UIState::engagedChanged, [toggle](bool engaged) {
        toggle->setEnabled(!engaged);
      });

      QObject::connect(toggle, &ParamControlSP::toggleFlipped, [=](bool state) {
        params.putBool("OnroadCycleRequested", true);
      });
    }

    list->addItem(toggle);
    toggles[param.toStdString()] = toggle;
    param_watcher->addParam(param);
  }

  sunnyFeaturesScroller = new ScrollViewSP(list, this);
  vlayout->addWidget(sunnyFeaturesScroller);

  main_layout->addWidget(sunnyFeaturesScreen);
}

void SunnyFeaturesPanel::paramsRefresh() {
  if (!isVisible()) {
    return;
  }

  for (auto toggle : toggles) {
    toggle.second->refresh();
  }
}
