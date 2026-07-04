/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/offroad/settings/visuals_panel.h"

VisualsPanel::VisualsPanel(QWidget *parent) : QWidget(parent) {
  param_watcher = new ParamWatcher(this);
  connect(param_watcher, &ParamWatcher::paramChanged, [=](const QString &param_name, const QString &param_value) {
    paramsRefresh();
  });

  main_layout = new QStackedLayout(this);
  ListWidgetSP *list = new ListWidgetSP(this, false);

  sunnypilotScreen = new QWidget(this);
  QVBoxLayout* vlayout = new QVBoxLayout(sunnypilotScreen);
  vlayout->setContentsMargins(50, 20, 50, 20);

  std::vector<std::tuple<QString, QString, QString, QString, bool> > toggle_defs{
    {
      "BlindSpot",
      tr("盲区警告提示"),
      tr("开启后，当盲区监测 (BSM) 检测到盲区内有车辆时，屏幕两侧将显示警告图标。需要车辆支持 BSM 功能。"),
      "../assets/offroad/icon_monitoring.png",
      false,
    },
    {
      "RainbowMode",
      tr("彩虹路径模式"),
      RainbowizeWords(tr("在模型规划的路径上显示美丽的彩虹渐变效果。")) + "<br/><i>" + tr("此功能")+ " <b>" + tr("不会") + "</b> " + tr("影响驾驶行为。") + "</i>",
      "../assets/offroad/icon_monitoring.png",
      false,
    },
  };

  // Add regular toggles first
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

  // Visuals: Display Metrics below Chevron
  std::vector<QString> chevron_info_settings_texts{tr("关闭"), tr("距离"), tr("速度"), tr("时间"), tr("全部")};
  chevron_info_settings = new ButtonParamControlSP(
    "ChevronInfo", tr("前车信息显示"), tr("在跟踪前车的箭头下方显示距离/速度/TTC 等实用指标（仅适用于 openpilot 纵向控制的车型）。"),
    "",
    chevron_info_settings_texts,
    200);
  chevron_info_settings->showDescription();
  list->addItem(chevron_info_settings);
  param_watcher->addParam("ChevronInfo");

  // Visuals: Developer UI Info (Dev UI)
  std::vector<QString> dev_ui_settings_texts{tr("关闭"), tr("右侧"), tr("右侧 &&\n底部")};
  dev_ui_settings = new ButtonParamControlSP(
    "DevUIInfo", tr("开发者界面"), tr("显示来自各模块的实时参数和指标数据。"),
    "",
    dev_ui_settings_texts,
    380);
  list->addItem(dev_ui_settings);

  sunnypilotScroller = new ScrollViewSP(list, this);
  vlayout->addWidget(sunnypilotScroller);

  main_layout->addWidget(sunnypilotScreen);
}

void VisualsPanel::paramsRefresh() {
  if (!isVisible()) {
    return;
  }

  for (auto toggle : toggles) {
    toggle.second->refresh();
  }

  if (chevron_info_settings) {
    chevron_info_settings->refresh();
  }
  if (dev_ui_settings) {
    dev_ui_settings->refresh();
  }
}
