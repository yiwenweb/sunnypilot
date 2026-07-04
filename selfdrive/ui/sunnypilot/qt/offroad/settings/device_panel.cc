/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/offroad/settings/device_panel.h"

#include "common/watchdog.h"
#include "selfdrive/ui/qt/qt_window.h"

DevicePanelSP::DevicePanelSP(SettingsWindowSP *parent) : DevicePanel(parent) {
  QGridLayout *device_grid_layout = new QGridLayout();
  device_grid_layout->setSpacing(30);
  device_grid_layout->setHorizontalSpacing(5);
  device_grid_layout->setVerticalSpacing(25);

  std::vector<std::tuple<QString, QString, QString>> device_btns = {
    {"quietModeBtn", tr("静音模式"), "QuietMode"},
    {"dcamBtn", tr("驾驶员摄像头预览"), ""},
    {"retrainingBtn", tr("训练指南"), ""},
    {"regulatoryBtn", tr("法规信息"), ""},
    {"translateBtn", tr("语言"), ""},
    {"resetParams", tr("重置设置"), ""},
  };

  int row = 0, col = 0;
  for (const auto &[id, text, param] : device_btns) {
    if (id == "regulatoryBtn" && !Hardware::TICI()) {
      continue;
    }

    auto *btn = new PushButtonSP(text, 750, this, param);
    btn->setObjectName(id);
    buttons[id] = btn;

    if (col==0) {
      device_grid_layout->addWidget(btn, row, col, Qt::AlignLeft);
      col++;
    } else {
      device_grid_layout->addWidget(btn, row, col, Qt::AlignRight);
      col=0;
      row++;
    }
  }

  connect(buttons["dcamBtn"], &PushButtonSP::clicked, [=]() { emit showDriverView(); });

  connect(buttons["quietModeBtn"], &PushButtonSP::clicked, buttons["quietModeBtn"], &PushButtonSP::updateButton);

  connect(buttons["retrainingBtn"], &PushButtonSP::clicked, [=]() {
    if (ConfirmationDialog::confirm(tr("确定要查看训练指南吗？"), tr("查看"), this)) {
      emit reviewTrainingGuide();
    }
  });

  if (Hardware::TICI()) {
    connect(buttons["regulatoryBtn"], &PushButtonSP::clicked, [=]() {
      const std::string txt = util::read_file("../assets/offroad/fcc.html");
      ConfirmationDialog::rich(QString::fromStdString(txt), this);
    });
  }

  connect(buttons["translateBtn"], &PushButtonSP::clicked, [=]() {
    QMap<QString, QString> langs = getSupportedLanguages();
    QString selection = MultiOptionDialog::getSelection(tr("Select a language"), langs.keys(), langs.key(uiState()->language), this);
    if (!selection.isEmpty()) {
      // put language setting, exit Qt UI, and trigger fast restart
      params.put("LanguageSetting", langs[selection].toStdString());
      qApp->exit(18);
      watchdog_kick(0);
    }
  });

  connect(buttons["resetParams"], &PushButtonSP::clicked, this, &DevicePanelSP::resetSettings);

  // Max Time Offroad
  maxTimeOffroad = new MaxTimeOffroad();
  connect(maxTimeOffroad, &OptionControlSP::updateLabels, maxTimeOffroad, &MaxTimeOffroad::refresh);
  addItem(maxTimeOffroad);

    toggleDeviceBootMode = new ButtonParamControlSP("DeviceBootMode", tr("唤醒行为"), "", "", {"默认", "始终离线"}, 375, true);
  addItem(toggleDeviceBootMode);

  connect(toggleDeviceBootMode, &ButtonParamControlSP::buttonClicked, this, [=](int index) {
    params.put("DeviceBootMode", QString::number(index).toStdString());
    updateState();
  });

  interactivityTimeout =  new OptionControlSP("InteractivityTimeout", tr("交互超时"),
                                     tr("自定义设置界面超时时间。"
                                        "\n超过此时间无交互操作时，设置界面将自动关闭。"),
                                     "", {0, 120}, 10, true, nullptr, false);

  connect(interactivityTimeout, &OptionControlSP::updateLabels, [=]() {
    updateState();
  });

  addItem(interactivityTimeout);
  
  // Brightness
  brightness = new Brightness();
  connect(brightness, &OptionControlSP::updateLabels, brightness, &Brightness::refresh);
  addItem(brightness);

  addItem(device_grid_layout);

  // offroad mode and power buttons

  QHBoxLayout *power_layout = new QHBoxLayout();
  power_layout->setSpacing(25);

  PushButtonSP *rebootBtn = new PushButtonSP(tr("重启"), 750, this);
  rebootBtn->setStyleSheet(rebootButtonStyle);
  power_layout->addWidget(rebootBtn);
  QObject::connect(rebootBtn, &PushButtonSP::clicked, this, &DevicePanelSP::reboot);

  PushButtonSP *poweroffBtn = new PushButtonSP(tr("关机"), 750, this);
  poweroffBtn->setStyleSheet(powerOffButtonStyle);
  power_layout->addWidget(poweroffBtn);
  QObject::connect(poweroffBtn, &PushButtonSP::clicked, this, &DevicePanelSP::poweroff);

  if (!Hardware::PC()) {
    connect(uiState(), &UIState::offroadTransition, poweroffBtn, &PushButtonSP::setVisible);
  }

  offroadBtn = new PushButtonSP(tr("离线模式"));
  offroadBtn->setFixedWidth(power_layout->sizeHint().width());
  QObject::connect(offroadBtn, &PushButtonSP::clicked, this, &DevicePanelSP::setOffroadMode);

  QVBoxLayout *power_group_layout = new QVBoxLayout();
  power_group_layout->setSpacing(25);
  power_group_layout->addWidget(offroadBtn, 0, Qt::AlignHCenter);
  power_group_layout->addLayout(power_layout);

  addItem(power_group_layout);

  std::vector always_enabled_btns = {
    rebootBtn,
    poweroffBtn,
    offroadBtn,
    buttons["quietModeBtn"],
  };

  QObject::connect(uiState(), &UIState::offroadTransition, [=](bool offroad) {
    for (auto btn : findChildren<PushButtonSP*>()) {
      bool always_enabled = std::find(always_enabled_btns.begin(), always_enabled_btns.end(), btn) != always_enabled_btns.end();

      if (!always_enabled) {
        btn->setEnabled(offroad);
      }
    }
  });
}

void DevicePanelSP::setOffroadMode() {
  if (!uiState()->engaged()) {
    if (params.getBool("OffroadMode")) {
      if (ConfirmationDialog::confirm(tr("确定要退出始终离线模式吗？"), tr("确认"), this)) {
        // Check engaged again in case it changed while the dialog was open
        if (!uiState()->engaged()) {
          params.remove("OffroadMode");
        }
      }
    } else {
      if (ConfirmationDialog::confirm(tr("确定要进入始终离线模式吗？"), tr("确认"), this)) {
        // Check engaged again in case it changed while the dialog was open
        if (!uiState()->engaged()) {
          params.putBool("OffroadMode", true);
        }
      }
    }
  } else {
    ConfirmationDialog::alert(tr("请解除接合后再进入始终离线模式"), this);
  }

  updateState();
}

void DevicePanelSP::resetSettings() {
  if (ConfirmationDialog::confirm(tr("确定要重置所有 sunnypilot 设置为默认值吗？重置后无法恢复。"), tr("重置"), this)) {
    if (ConfirmationDialog::confirm(tr("重置操作不可撤销，请确认。"), tr("确认"), this)) {
      const std::vector<std::string> keys = params.allKeys();
      for (const auto& key : keys) {
        params.remove(key);
      }

      Hardware::reboot();
    }
  }
}

void DevicePanelSP::showEvent(QShowEvent *event) {
  updateState();
}

void DevicePanelSP::updateState() {
  if (!isVisible()) {
    return;
  }

  bool offroad_mode_param = params.getBool("OffroadMode");
  offroadBtn->setText(offroad_mode_param ? tr("退出始终离线") : tr("始终离线"));
  offroadBtn->setStyleSheet(offroad_mode_param ? alwaysOffroadStyle : autoOffroadStyle);

  DeviceSleepModeStatus currStatus = DeviceSleepModeStatus::DEFAULT;
  if (params.get("DeviceBootMode") == "1") {
    currStatus = DeviceSleepModeStatus::OFFROAD;
  }
  toggleDeviceBootMode->setDescription(deviceSleepModeDescription(currStatus));

  QString timeoutValue = QString::fromStdString(params.get("InteractivityTimeout"));
  if (timeoutValue == "0" || timeoutValue.isEmpty()) {
    interactivityTimeout->setLabel("Default");
  } else {
    interactivityTimeout->setLabel(timeoutValue + "s");
  }
}
