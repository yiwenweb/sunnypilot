import numpy as np
from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.lateral import apply_driver_steer_torque_limits
from opendbc.car.byd import bydcan
from opendbc.car.byd.values import CarControllerParams

VisualAlert = structs.CarControl.HUDControl.VisualAlert
ButtonType = structs.CarState.ButtonEvent.Type
LongCtrlState = structs.CarControl.Actuators.LongControlState


class CarController(CarControllerBase):
  def __init__(self, dbc_names, CP, CP_SP):
    super().__init__(dbc_names, CP, CP_SP)

    self.packer = CANPacker(dbc_names[Bus.pt])

    self.frame = 0
    self.last_steer_frame = 0
    self.last_acc_frame = 0

    self.apply_torque_last = 0

    self.mpc_lkas_counter = 0
    self.mpc_acc_counter = 0
    self.eps_fake318_counter = 0

    self.lkas_req_prepare = 0
    self.lkas_active = 0
    self.lat_safeoff = 0

    self.steer_softstart_limit = 0
    self.steerRateLimActive = False
    self.steerRateLim = 1.0

    # anti-stall protection state
    self.stall_counter = 0
    self.release_counter = 0

    # LOCK3: EPS unilateral withdrawal detection + auto re-handshake recovery state
    self.eps_withdraw_counter = 0
    self.eps_recover_cooldown = 0
    self.eps_recover_attempts = 0

    self.first_start = True
    self.rfss = 0
    self.sss = 0

    self.apply_accel_last = 0


  def update(self, CC, CC_SP, CS, now_nanos):
    can_sends = []

    if (self.frame - self.last_steer_frame) >= CarControllerParams.STEER_STEP:

      # Resolve counter mismatch problem
      if self.first_start:
        self.mpc_lkas_counter = int(CS.acc_mpc_state_counter + 1) & 0xF
        self.mpc_acc_counter = int(CS.acc_cmd_counter + 1) & 0xF
        self.eps_fake318_counter = int(CS.eps_state_counter + 1) & 0xF
        self.first_start = False

      apply_torque = 0

      if CC.latActive:
        if self.lkas_active:
          steer_desire = CC.actuators.torque

          if CarControllerParams.USE_STEERING_SPEED_LIMITER:
            rate_limit = np.interp(CS.out.aEgo, [8.3, 27.8], [132, 64])
            delta_rate = CS.steeringRateDegAbs - rate_limit

            if delta_rate < 0:
              self.steerRateLim -= 0.005 * delta_rate
              if delta_rate < -0.05:
                self.steerRateLimActive = False
              if self.steerRateLim > 1.0:
                self.steerRateLim = 1.0
                self.steerRateLimActive = False
            else:
              if self.steerRateLimActive:
                self.steerRateLim -= 0.005 * delta_rate
              else:
                self.steerRateLim = steer_desire
                self.steerRateLimActive = True
              if self.steerRateLim < 0:
                self.steerRateLim = 0

            new_steer_pu = np.clip(steer_desire, -self.steerRateLim, self.steerRateLim)
          else:
            new_steer_pu = steer_desire

          new_steer = int(round(new_steer_pu * CarControllerParams.STEER_MAX))

          # 低速扭矩封顶: 按车速限制 |扭矩| 上限, 复刻门总 0.98 实测包络,
          # 防止低速大扭矩把方向盘顶到机械限位导致 EPS 过载 TorqueFailed 锁死。
          if CarControllerParams.USE_LOWSPEED_TORQUE_LIMIT:
            tq_ceiling = int(np.interp(CS.out.vEgo,
                                       CarControllerParams.LOWSPEED_TQ_BP,
                                       CarControllerParams.LOWSPEED_TQ_V))
            new_steer = np.clip(new_steer, -tq_ceiling, tq_ceiling)

          if self.steer_softstart_limit < CarControllerParams.STEER_MAX:
            self.steer_softstart_limit = self.steer_softstart_limit + CarControllerParams.STEER_SOFTSTART_STEP
            new_steer = np.clip(new_steer, -self.steer_softstart_limit, self.steer_softstart_limit)

          apply_torque = apply_driver_steer_torque_limits(new_steer, self.apply_torque_last,
                                                          CS.out.steeringTorque, CarControllerParams)

          # 门总接管序列: Act=1 后必须等 EPS CruiseActivated=1 才发扭矩。
          # 在 Cru=0 时发非零扭矩 -> panda 的 steer_req=Active&&CruiseActivated 判为"未接管却
          # 发力" -> 拦截 -> EPS 收到 Active 却收不到扭矩 -> 电机 MainTorque=0 -> 0.7s后
          # TorqueFailed 锁死 (LOCK1 实证: Cru=0 时 OPout 已爬到160, MainTq 全程0)。
          # 故 Cru 未到达前强制扭矩=0 且软起点归零, Cru 到达后从0平滑爬升 (对齐门总)。
          if not CS.eps_cruise_activated:
            apply_torque = 0
            self.steer_softstart_limit = 0
            self.steerRateLimActive = False
            self.steerRateLim = 1.0
          # Detect low-speed sustained near-max torque (wheel winding to lock while torque
          # pins at STEER_MAX) and force a brief torque release so the BYD EPS overload
          # timer resets before it asserts TorqueFailed.
          if CarControllerParams.ANTISTALL_ENABLE:
            P = CarControllerParams
            pushing_hard = (CS.out.vEgo < P.ANTISTALL_SPEED and
                            abs(apply_torque) >= P.ANTISTALL_TORQUE)

            if self.release_counter > 0:
              # in release window: hold torque at 0 to let the EPS overload timer reset
              self.release_counter -= 1
              apply_torque = apply_driver_steer_torque_limits(0, self.apply_torque_last,
                                                              CS.out.steeringTorque, CarControllerParams)
              if self.release_counter == 0:
                self.stall_counter = 0
            elif pushing_hard:
              self.stall_counter += 1
              if self.stall_counter >= P.ANTISTALL_TRIGGER_FRAMES:
                # sustained too long: enter release window
                self.release_counter = P.ANTISTALL_RELEASE_FRAMES
            else:
              # torque/speed back to normal: decay the counter
              self.stall_counter = max(0, self.stall_counter - 2)

            # debug: only print while the guard is active to avoid spam
            if self.stall_counter > 0 or self.release_counter > 0:
              print("ANTISTALL v=%.2f tq=%d ang=%.0f | cnt=%d release=%d %s" % (
                CS.out.vEgo, apply_torque, CS.out.steeringAngleDeg,
                self.stall_counter, self.release_counter,
                "<<< RELEASING" if self.release_counter > 0 else ("PUSH?" if pushing_hard else "")))

          # LOCK3 保护 + 自动重握手恢复 (实证 20260701 LOCK1 dump 逐帧):
          #   -0.52s  byte0=0xFA Prep0 Cru1 TqF0 MainTq75   稳定接管中
          #   -0.50s  byte0=0xFB Prep1 Cru1 TqF0 MainTq66   ★EPS 主动 Prepared 0->1 = 发起重握手请求
          #   -0.42s  byte0=0xFB Prep1 Cru1 TqF0 MainTq 0   EPS 停止出力, 等 OP 配合重握手
          #   ...     (持续 0.5s: Prep1 Cru1 TqF0 MainTq0, drvTq≈0 -> 疑因脱手触发)
          #   +0.00s  byte0=0xFC Prep0 Cru0 TqF1            OP 未配合 -> EPS 判超时 -> 锁死
          # 关键: EPS 不是猝死, 而是先给了 ~0.5s 窗口(Prep=1)等 OP 重新握手。我们过去继续发老扭矩
          # (MainTq 却=0)形成错配, 等不到正确响应才锁。门总的做法是立即配合重走握手。
          # 修复: 接管中若 EPS 出力≈0 而我方仍发较大扭矩 -> 判 EPS 发起重握手 -> 立即松扭矩+归零
          # 握手状态, 交回下方 else 分支自动重新握手 (Prep=1 时下一帧即 active=1, 从0软起恢复)。
          # 冷却期避免抖动; 连续多次失败(EPS 拒绝重握手)则彻底退出并由 steerFaultTemporary 报警。
          if self.eps_recover_cooldown > 0:
            self.eps_recover_cooldown -= 1

          if CarControllerParams.LOCK3_ENABLE and CS.eps_cruise_activated and self.eps_recover_cooldown == 0:
            eps_out = abs(int(CS.out.steeringTorqueEps))
            cmd_big = abs(apply_torque) >= CarControllerParams.LOCK3_CMD_TORQUE
            if eps_out <= CarControllerParams.LOCK3_EPS_ZERO and cmd_big:
              self.eps_withdraw_counter += 1
            else:
              self.eps_withdraw_counter = max(0, self.eps_withdraw_counter - 1)
              if eps_out > CarControllerParams.LOCK3_EPS_ZERO:
                # EPS 恢复出力 = 重握手成功, 清零尝试计数
                self.eps_recover_attempts = 0

            if self.eps_withdraw_counter >= CarControllerParams.LOCK3_TRIGGER_FRAMES:
              # 确认 EPS 撤出 (MainTq≈0 而我方在发力): 立即松手并触发重握手
              apply_torque = 0
              self.lkas_active = 0
              self.steer_softstart_limit = 0
              self.steerRateLimActive = False
              self.steerRateLim = 1.0
              self.eps_withdraw_counter = 0
              self.eps_recover_attempts += 1
              if self.eps_recover_attempts >= CarControllerParams.LOCK3_MAX_ATTEMPTS:
                # 反复重握手仍失败 -> EPS 坚持要驾驶员接管, 彻底退出握手不再自动恢复
                self.lkas_req_prepare = 0
                self.eps_recover_cooldown = CarControllerParams.LOCK3_GIVEUP_COOLDOWN
                print("LOCK3 GIVE-UP v=%.2f attempts=%d -> disengage, alert driver" % (
                  CS.out.vEgo, self.eps_recover_attempts))
              else:
                # 请求重握手: 下一帧 else 分支见 Prep=1 即 active=1 从0软起恢复
                self.lkas_req_prepare = 1
                self.eps_recover_cooldown = CarControllerParams.LOCK3_RECOVER_COOLDOWN
                print("LOCK3 EPS-WITHDRAW v=%.2f OPtq=%d MainTq=%d -> release+rehandshake (attempt %d)" % (
                  CS.out.vEgo, int(self.apply_torque_last), int(CS.out.steeringTorqueEps),
                  self.eps_recover_attempts))

        else:
          if CS.lkas_prepared:
            self.lkas_active = 1.0
            self.steerRateLimActive = False
            self.steerRateLim = 1.0
            self.lkas_req_prepare = 0
            self.steer_softstart_limit = 0
          else:
            self.lkas_req_prepare = 1

      else:
        # 退出接管 (latActive=0): 门总的退出序列是先把扭矩按下降速率平滑降到接近0, 再松手
        # (Act 1->0)。我们过去在此直接 apply_torque=0 硬清零, 当时若正出满扭矩(-195), EPS
        # 电机实打实出着力, 命令一帧消失 -> 判异常 TorqueFailed 锁死 (LOCK2 实证)。
        # 修复: 若仍在接管且 EPS 巡航仍激活且上帧扭矩还较大, 则保持 lkas_active=1, 用速率限制
        # 把扭矩朝0平滑收敛(每帧≤STEER_DELTA_DOWN); 待扭矩接近0或巡航已退出, 再完全复位握手。
        if self.lkas_active and CS.eps_cruise_activated and abs(self.apply_torque_last) > CarControllerParams.STEER_DELTA_DOWN:
          apply_torque = apply_driver_steer_torque_limits(0, self.apply_torque_last,
                                                          CS.out.steeringTorque, CarControllerParams)
          # 收尾期间保持 active/prepare 不变, 仅让扭矩平滑归零
        else:
          apply_torque = 0
          self.lkas_req_prepare = 0
          self.steerRateLimActive = False
          self.steerRateLim = 1.0
          self.lkas_active = 0
          self.steer_softstart_limit = 0
          self.stall_counter = 0
          self.release_counter = 0

      self.apply_torque_last = apply_torque

      self.mpc_lkas_counter = int(self.mpc_lkas_counter + 1) & 0xF
      self.eps_fake318_counter = int(self.eps_fake318_counter + 1) & 0xF
      self.last_steer_frame = self.frame

      # send steering command, op to esc
      can_sends.append(bydcan.create_steering_control(self.packer, self.CP, CS.cam_lkas,
          self.apply_torque_last, self.lkas_req_prepare, self.lkas_active, CC.hudControl, self.mpc_lkas_counter))

      # Send fake 0x318 (EPS->MPC) to trick MPC into thinking EPS is executing MPC's commands.
      # Without this, MPC detects conflict and may cancel LKAS or generate DTC.
      can_sends.append(bydcan.create_fake_318(self.packer, self.CP, CS.esc_eps,
                                              CS.mpc_laks_output, CS.mpc_laks_reqprepare, CS.mpc_laks_active,
                                              True, self.eps_fake318_counter))

    if (self.frame + 1 - self.last_acc_frame) >= CarControllerParams.ACC_STEP:
      accel = np.clip(CC.actuators.accel, CarControllerParams.ACCEL_MIN, CarControllerParams.ACCEL_MAX)

      if CC.longActive:
        stopping = CC.actuators.longControlState == LongCtrlState.stopping
        starting = CC.actuators.longControlState == LongCtrlState.starting
        running = CC.actuators.longControlState == LongCtrlState.pid

        if stopping and accel < -0.1:
            self.rfss = 0
            self.sss = CS.out.standstill

        elif starting and accel > 0.1 and CS.out.vEgo < 0.8:
          self.rfss = CS.out.standstill
          self.sss = 0

        elif running:
          self.rfss = 0
          self.sss = 0

      else:
        accel = 0
        self.sss = 0
        self.rfss = 0

      self.mpc_acc_counter = int(self.mpc_acc_counter + 1) & 0xF
      can_sends.append(bydcan.acc_cmd(self.packer, self.CP, CS.cam_acc, CS.mrr_leading_dist, accel, self.rfss, self.sss, CC.longActive, self.mpc_acc_counter))

      self.apply_accel_last = accel
      self.last_acc_frame = self.frame + 1

    new_actuators = CC.actuators.as_builder()
    new_actuators.torque = self.apply_torque_last / CarControllerParams.STEER_MAX
    new_actuators.torqueOutputCan = self.apply_torque_last
    new_actuators.accel = float(self.apply_accel_last)
    new_actuators.steeringAngleDeg = float(CS.out.steeringAngleDeg)

    self.frame += 1
    return new_actuators, can_sends
