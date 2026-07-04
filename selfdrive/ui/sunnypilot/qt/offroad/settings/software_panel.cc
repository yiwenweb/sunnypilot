/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/offroad/settings/software_panel.h"

SoftwarePanelSP::SoftwarePanelSP(QWidget *parent) : SoftwarePanel(parent) {
  // branch selector
  QObject::disconnect(targetBranchBtn, nullptr, nullptr, nullptr);
  connect(targetBranchBtn, &ButtonControlSP::clicked, [=]() {
    if (Hardware::get_device_type() == cereal::InitData::DeviceType::TICI) {
      auto current = params.get("GitBranch");
      QStringList allBranches = QString::fromStdString(params.get("UpdaterAvailableBranches")).split(",");
      QStringList branches;
      for (const QString &b : allBranches) {
        if (b.endsWith("-tici")) {
          branches.append(b);
        }
      }

      for (QString b : {current.c_str(), "master-tici", "staging-tici", "release-tici"}) {
        auto i = branches.indexOf(b);
        if (i >= 0) {
          branches.removeAt(i);
          branches.insert(0, b);
        }
      }

      QString cur = QString::fromStdString(params.get("UpdaterTargetBranch"));
      QString selection = MultiOptionDialog::getSelection(tr("选择分支"), branches, cur, this);
      if (!selection.isEmpty()) {
        params.put("UpdaterTargetBranch", selection.toStdString());
        targetBranchBtn->setValue(QString::fromStdString(params.get("UpdaterTargetBranch")));
        checkForUpdates();
      }
    } else {
      InputDialog d(tr("搜索分支"), this, tr("输入搜索关键词，留空则列出全部分支。"), false);
      d.setMinLength(0);
      const int ret = d.exec();
      if (ret) {
        searchBranches(d.text());
      }
    }
  });

  // Disable Updates toggle
  disableUpdatesToggle = new ParamControl("DisableUpdates",
    tr("禁用更新"),
    tr("启用后将禁止软件更新。<b>需要重启才能生效。</b>"),
    "../assets/icons/icon_warning.png",
    this, true);
  disableUpdatesToggle->showDescription();
  addItem(disableUpdatesToggle);
  connect(disableUpdatesToggle, &ParamControl::toggleFlipped, this, &SoftwarePanelSP::handleDisableUpdatesToggled);
  connect(uiState(), &UIState::offroadTransition, this, &SoftwarePanelSP::updateDisableUpdatesToggle);
  updateDisableUpdatesToggle(!uiState()->scene.started);
}

/**
 * @brief Searches for available branches based on a query string, presents the results in a dialog,
 * and updates the target branch if a selection is made.
 *
 * This function filters the list of branches based on the provided query, and displays the filtered branches in a selection dialog.
 * If a branch is selected, the "UpdaterTargetBranch" parameter is updated and a check for updates is triggered.
 * If no branches are found matching the query, an alert dialog is displayed.
 *
 * @param query The search query string.
 */
void SoftwarePanelSP::searchBranches(const QString &query) {

  QStringList branches = QString::fromStdString(params.get("UpdaterAvailableBranches")).split(",");
  QStringList results = searchFromList(query, branches);
  results.sort();

  if (results.isEmpty()) {
    ConfirmationDialog::alert(tr("未找到匹配关键词的分支: %1").arg(query), this);
    return;
  }

  QString selected_branch = MultiOptionDialog::getSelection(tr("选择分支"), results, "", this);

  if (!selected_branch.isEmpty()) {
    params.put("UpdaterTargetBranch", selected_branch.toStdString());
    targetBranchBtn->setValue(selected_branch);
    checkForUpdates();
  }
}

void SoftwarePanelSP::handleDisableUpdatesToggled(bool state) {
  if (ConfirmationDialog::confirm(tr("%1更新需要重启。<br>是否现在重启？")
      .arg(state ? "禁用" : "启用"), tr("重启"), this)) {
    params.putBool("DoReboot", true);
  } else {
    params.putBool("DisableUpdates", !state);
    disableUpdatesToggle->refresh();
  }
}

void SoftwarePanelSP::updateDisableUpdatesToggle(bool offroad) {
  bool enabled = offroad;
  disableUpdatesToggle->setEnabled(enabled);
  disableUpdatesToggle->setDescription(enabled
    ? tr("启用后将禁止软件更新。<br><b>需要重启才能生效。</b>")
    : tr("请先启用始终离线模式或关闭车辆后再调整此开关。"));
}

void SoftwarePanelSP::showEvent(QShowEvent *event) {
  SoftwarePanel::showEvent(event);
  updateDisableUpdatesToggle(!uiState()->scene.started);
  disableUpdatesToggle->showDescription();
}
