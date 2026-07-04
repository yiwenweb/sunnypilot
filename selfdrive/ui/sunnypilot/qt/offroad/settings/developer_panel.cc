/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */
#include "selfdrive/ui/sunnypilot/qt/offroad/settings/developer_panel.h"
#include "selfdrive/ui/sunnypilot/qt/widgets/external_storage.h"

DeveloperPanelSP::DeveloperPanelSP(SettingsWindow *parent) : DeveloperPanel(parent) {

  #ifndef __APPLE__
  addItem(new ExternalStorageControl());
  #endif

  // Advanced Controls Toggle
  showAdvancedControls = new ParamControlSP("ShowAdvancedControls", tr("显示高级控制"), tr("切换 sunnypilot 高级控制的可见性。\n此开关仅控制显示/隐藏，不影响功能的实际启用状态。"), "");
  addItem(showAdvancedControls);

  QObject::connect(showAdvancedControls, &ParamControlSP::toggleFlipped, this, [=](bool) {
    AbstractControlSP::UpdateAllAdvancedControls();
    updateToggles(!uiState()->scene.started);
  });
  showAdvancedControls->showDescription();

  // Github Runner Toggle
  enableGithubRunner = new ParamControlSP("EnableGithubRunner", tr("启用 GitHub Runner 服务"), tr("启用或禁用 GitHub Runner 服务。"), "", this, true);
  addItem(enableGithubRunner);

  // Copyparty Toggle
  enableCopyparty = new ParamControlSP("EnableCopyparty", tr("启用 Copyparty 服务"), tr("Copyparty 是一款功能强大的文件服务器，可通过浏览器下载路线数据、查看日志、甚至编辑文件。需要通过 IP 地址本地连接到您的 comma 设备。"), "", this, false);
  addItem(enableCopyparty);

  // Quickboot Mode Toggle
  prebuiltToggle = new ParamControlSP("QuickBootToggle", tr("启用快速启动模式"), tr(""), "", this, true);
  addItem(prebuiltToggle);

  QObject::connect(prebuiltToggle, &ParamControl::toggleFlipped, [=](bool state) {
    QString prebuiltPath = "/data/openpilot/prebuilt";
    state ? QFile(prebuiltPath).open(QIODevice::WriteOnly) : QFile::remove(prebuiltPath);
    prebuiltToggle->refresh();
  });
  prebuiltToggle->setVisible(false);

  // Error log button
  errorLogBtn = new ButtonControlSP(tr("错误日志"), tr("查看"), tr("查看 sunnypilot 崩溃的错误日志。"));
  connect(errorLogBtn, &ButtonControlSP::clicked, [=]() {
    QFileInfo file("/data/community/crashes/error.log");
    QString text;
    if (file.exists()) {
      text = "<b>" + file.lastModified().toString("dd-MMM-yyyy hh:mm:ss ").toUpper() + "</b><br><br>";
    }
    text += QString::fromStdString(util::read_file("/data/community/crashes/error.log"));
    ConfirmationDialog::rich(text, this);
  });
  addItem(errorLogBtn);

  QObject::connect(uiState(), &UIState::offroadTransition, this, &DeveloperPanelSP::updateToggles);

  is_release = params.getBool("IsReleaseBranch");
  is_tested = params.getBool("IsTestedBranch");
  is_development = params.getBool("IsDevelopmentBranch");
}

void DeveloperPanelSP::updateToggles(bool offroad) {
  bool disable_updates = params.getBool("DisableUpdates");

  prebuiltToggle->setVisible(!is_release && !is_tested && !is_development);
  prebuiltToggle->setEnabled(disable_updates);
  params.putBool("QuickBootToggle", QFile::exists("/data/openpilot/prebuilt"));
  prebuiltToggle->refresh();

  prebuiltToggle->setDescription(disable_updates
    ? tr("开启后将创建预编译文件以加速启动。关闭后立即删除预编译文件，使本地修改的 C++ 文件可以重新编译。"
         "<br><br><b>要在设备上编辑 C++ 文件，必须先关闭此开关以允许重新编译。</b>")
    : tr("快速启动模式需要先禁用更新。<br>请先在\"软件\"面板中启用\"禁用更新\"。"));
  prebuiltToggle->showDescription();

  enableGithubRunner->setVisible(!is_release);
  errorLogBtn->setVisible(!is_release);
  showAdvancedControls->setEnabled(true);
}

void DeveloperPanelSP::showEvent(QShowEvent *event) {
  DeveloperPanel::showEvent(event);
  AbstractControlSP::UpdateAllAdvancedControls();
  updateToggles(!uiState()->scene.started);
}
