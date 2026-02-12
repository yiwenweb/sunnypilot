#pragma once

#include "opendbc/safety/safety_declarations.h"

/*
=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准

BYD Body Safety Hooks (车身安全钩子)
适配车型：BYD Tang DM 2018（18款唐DM）
核心功能：
1. RX钩子：监听0x201报文，触发controls_allowed（控制允许）
2. TX钩子：控制车身CAN报文发送权限，仅允许白名单报文在非允许状态下发送
3. 特殊逻辑：CAN刷写报文（0x250）即使无控制权限也允许发送，避免刷写失败
*/

/**
 * @brief 车身CAN接收钩子 - 监听关键报文更新控制允许状态
 * @param msg 接收到的CAN报文结构体
 * @note 18款唐DM：0x201为车身状态报文，收到则判定为车辆通讯正常，允许控制
 */
static void body_rx_hook(const CANPacket_t *msg) {
  // 监听0x201报文（车身状态），收到则设置controls_allowed=true
  if (msg->addr == 0x201U) {
    controls_allowed = true;
  }
}

/**
 * @brief 车身CAN发送钩子 - 过滤非法发送的报文
 * @param msg 待发送的CAN报文结构体
 * @return bool: true=允许发送，false=禁止发送
 * @note 核心规则：
 * 1. 非控制允许状态下，仅允许0x1（CAN刷写器）和0x250（刷写指令）报文发送
 * 2. 0x250报文需满足特定魔术字（0xdeadface + 0x0ab00b1e）才允许刷写
 */
static bool body_tx_hook(const CANPacket_t *msg) {
  bool tx = true;

  // 非控制允许状态下，仅允许0x1报文发送（CAN flasher）
  if (!controls_allowed && (msg->addr != 0x1U)) {
    tx = false;
  }

  // 特殊逻辑：允许CAN刷写模式报文（0x250）即使无控制权限也发送
  // 魔术字验证：前4字节=0xdeadface，后4字节=0x0ab00b1e，长度=8字节
  bool flash_msg = (msg->addr == 0x250U) && (GET_LEN(msg) == 8U);
  if (!controls_allowed && (GET_BYTES(msg, 0, 4) == 0xdeadfaceU) && 
      (GET_BYTES(msg, 4, 4) == 0x0ab00b1eU) && flash_msg) {
    tx = true;
  }

  return tx;
}

/**
 * @brief 车身安全配置初始化函数
 * @param param 安全配置参数（未使用）
 * @return safety_config: 初始化后的安全配置结构体
 * @note 18款唐DM专属配置：
 * - RX校验：仅监听0x201报文（100ms超时）
 * - TX白名单：0x250（刷写）、0x251（车身控制）、0x1（刷写器）
 * - 禁用报文转发：避免总线干扰
 */
static safety_config body_init(uint16_t param) {
  // RX校验列表：监听0x201报文（8字节，100ms超时，忽略校验和/计数器/质量位）
  static RxCheck body_rx_checks[] = {
    {.msg = {{0x201, 0, 8, 100U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
  };

  // TX白名单：允许发送的报文列表（body安全钩子管控）
  static const CanMsg BODY_TX_MSGS[] = {
    {0x250, 0, 8, .check_relay = false},  // CAN刷写指令（8字节）
    {0x250, 0, 6, .check_relay = false},  // CAN刷写指令（6字节）
    {0x251, 0, 5, .check_relay = false},  // 车身控制报文（5字节）
    {0x1, 0, 8, .check_relay = false}     // CAN刷写器报文（8字节）
  };

  UNUSED(param);  // 未使用的参数，避免编译警告
  // 构建安全配置结构体
  safety_config ret = BUILD_SAFETY_CFG(body_rx_checks, BODY_TX_MSGS);
  ret.disable_forwarding = true;  // 禁用CAN报文转发，防止总线冲突
  return ret;
}

// 车身安全钩子结构体（注册到openpilot安全框架）
const safety_hooks body_hooks = {
  .init = body_init,    // 初始化函数
  .rx = body_rx_hook,   // 接收钩子
  .tx = body_tx_hook    // 发送钩子
};