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

    # LOCK3: EPS 请求退出横向 (Prepared 0->1) 检测 + 快速松手退出 (对齐门总)
    self.eps_prepared_last = False
    self.eps_exit_release = 0
    self.eps_exit_wait = False

    # LOCK4: 退出收尾时等 EPS 电机(MainTorque)卸载再松手, 防司机对抗导致 MainTq 滞后锁死
    self.exit_dwell = 0

    # LOCK5: 重接管延迟出力 + 顶不动收回 (对齐门总)
    self.reengage_delay = 0    # 重接管后剩余的"强制0出力"帧数
    self.lkas_active_last = 0  # 上一帧 lkas_active, 用于检测 0->1 重接管沿
    self.stuck_counter = 0     # 大对抗且顶不动的持续帧数
    self.lock5_giveup = False  # 已进入"顶不动收回"放弃状态

    self.first_start = True
    self.rfss = 0
    self.sss = 0

    self.apply_accel_last = 0
    
    # 纵向控制优化
    self.speed_hyst_upper = False  # 超速抑制状态


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
          self.exit_dwell = 0   # 正在接管出力, 清退出收尾计数, 保证下次退出从0起

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

          # LOCK5: 重接管"延迟出力 + 顶不动收回" (对齐门总 byd_men_reengage_ramp 实证)
          if CarControllerParams.LOCK5_ENABLE:
            P = CarControllerParams
            # (a) 重接管延迟: lkas_active 0->1 (本帧刚接管) 后, 前 N 帧强制 0 出力,
            #     给 EPS 几帧稳定再出力 (门总大对抗重接管帧+0~+2 出力恒0)。
            if self.lkas_active and not self.lkas_active_last:
              self.reengage_delay = P.LOCK5_REENGAGE_DELAY_FRAMES
              self.stuck_counter = 0
              self.lock5_giveup = False
            if self.reengage_delay > 0:
              self.reengage_delay -= 1
              apply_torque = 0
              self.steer_softstart_limit = 0   # 保证延迟结束后从0慢软起

            # (d) 顶不动收回: 司机大力对抗(|drvTq|大) 且我们命令已出力(|out|>阈值) 但 EPS 电机
            #     (MainTorque)长期顶不上去(<阈值, 说明方向盘被司机压住电机跟不动) -> 判定"顶不动",
            #     持续超 STUCK_FRAMES 帧则把命令收回 0 放弃硬顶 (门总 drv0=-175 样例行为),
            #     避免长时间硬顶触发 TorqueFailed 锁死。待司机松手(drvTq 变小)再解除放弃、重新出力。
            drv_big = abs(int(CS.out.steeringTorque)) >= P.LOCK5_FIGHT_DRV_TQ
            out_big = abs(int(apply_torque)) >= P.LOCK5_STUCK_OUT
            eps_stuck = abs(int(CS.out.steeringTorqueEps)) < P.LOCK5_STUCK_MAINTQ
            if drv_big and out_big and eps_stuck:
              self.stuck_counter += 1
            elif not drv_big:
              self.stuck_counter = max(0, self.stuck_counter - 2)
              if self.stuck_counter == 0:
                self.lock5_giveup = False
            if self.stuck_counter >= P.LOCK5_STUCK_FRAMES:
              self.lock5_giveup = True
            if self.lock5_giveup:
              # 放弃硬顶: 命令按速率收回到0 (不松手退出, 只是不再顶), 待司机松手自然恢复
              apply_torque = apply_driver_steer_torque_limits(0, self.apply_torque_last,
                                                              CS.out.steeringTorque, CarControllerParams)
              print("LOCK5 GIVEUP drv=%d out=%d MainTq=%d stuck=%d -> release (like 门总 -175)" % (
                int(CS.out.steeringTorque), int(apply_torque), int(CS.out.steeringTorqueEps), self.stuck_counter))

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

          # LOCK3: EPS 请求退出横向 (Prepared 0->1) -> 立即快速松手退出 (完全对齐门总 0.98)
          # 门总日志实证 (byd_menmen_prep.py, 41段/1621s):
          #   Prepared 0->1 = EPS 主动请求"结束本次横向会话"(通常因驾驶员介入, drvTq 骤变或很大),
          #   之后 0.08~0.14s 内 byte0 -> 0xF8 (Prep0 Cru0 完全退出待机)。
          #   门总响应: 一见 Prepared 0->1, 2-3帧内把扭矩收到0, 随后 Active 置0 退出;
          #   全程 Active=0 占比 80%, ReqPrepare=1 占比 0% -> 门总【只快速退出, 从不重握手/硬顶】。
          # 我们锁死那次相反: Prepared 0->1 后仍继续发扭矩(76->90)、Active 保持1, 导致 Prepared 与
          #   MainTq 卡在 (1,0) 达 0.5s, EPS 等不到 OP 退出 -> TorqueFailed 锁死。
          # 故正确做法 = 抄门总: 检测 Prepared 上升沿 -> 进入"退出收尾", 按速率快速把扭矩收到0,
          #   期间锁定不重新 active(即使 else 分支想恢复也不允许), 待扭矩归0后 Active=0 干净退出。
          #   不重握手: 退出后由驾驶员松手 -> EPS 回到稳定态 -> 正常流程重新接管。
          prepared_rising = CarControllerParams.LOCK3_ENABLE and CS.lkas_prepared and not self.eps_prepared_last
          if prepared_rising and self.eps_exit_release == 0:
            self.eps_exit_release = CarControllerParams.LOCK3_EXIT_FRAMES
            print("LOCK3 EPS-EXIT-REQ v=%.2f OPtq=%d MainTq=%d drvTq=%d -> fast release+exit (like 门总)" % (
              CS.out.vEgo, int(self.apply_torque_last), int(CS.out.steeringTorqueEps), int(CS.out.steeringTorque)))

          if self.eps_exit_release > 0:
            # 退出收尾: 按速率把扭矩平滑收到0 (门总约2-3帧), 收到0即 Active=0 退出
            self.eps_exit_release -= 1
            apply_torque = apply_driver_steer_torque_limits(0, self.apply_torque_last,
                                                            CS.out.steeringTorque, CarControllerParams)
            if abs(apply_torque) <= CarControllerParams.STEER_DELTA_DOWN or self.eps_exit_release == 0:
              apply_torque = 0
              self.lkas_active = 0
              self.lkas_req_prepare = 0
              self.steer_softstart_limit = 0
              self.steerRateLimActive = False
              self.steerRateLim = 1.0
              self.eps_exit_release = 0
              # 退出后要求先看到 Prepared 落回0(EPS 回稳)才允许重新接管, 避免与 EPS 退出意图打架
              self.eps_exit_wait = True

        else:
          # 退出会话后的等待: EPS 退出时 Prepared 会保持1约7帧(0xFB)再落回0(0xF8)。
          # 若刚退出就见 Prepared=1 立即重新 active, 会与 EPS"要退出"意图对着干 -> 卡死风险。
          # 故先等 Prepared 落回0 清除等待标志, 之后才走原始握手逻辑重新接管。
          if self.eps_exit_wait:
            if not CS.lkas_prepared:
              self.eps_exit_wait = False   # EPS 已回稳, 解除等待
            self.lkas_req_prepare = 0
          elif CS.lkas_prepared:
            # 原始握手逻辑 (基线一致): 见 Prepared=1 即接管, 从0软起
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
        #
        # LOCK4 (20260702 实证补强): 仅靠"我们的命令降到0"不够。司机用力对抗时 EPS 电机
        # MainTorque 会滞后卡在高位(命令已0, MainTq仍47), 此时松手 Active=0 -> EPS 判"授权撤
        # 销但电机仍出力" -> 锁死。故退出收尾还须等 EPS MainTorque(=steeringTorqueEps)也降到
        # 阈值以下才松手; 命令归0后进入 exit_dwell 挂起等待电机卸载, 超时兜底防无限挂起。
        eps_mt = abs(int(CS.out.steeringTorqueEps))
        cmd_settling = self.lkas_active and CS.eps_cruise_activated and \
            abs(self.apply_torque_last) > CarControllerParams.STEER_DELTA_DOWN
        eps_loaded = (CarControllerParams.LOCK4_ENABLE and self.lkas_active and
                      CS.eps_cruise_activated and eps_mt > CarControllerParams.LOCK4_EPS_RELEASE_TQ and
                      self.exit_dwell < CarControllerParams.LOCK4_EXIT_MAX_FRAMES)
        if cmd_settling or eps_loaded:
          # 保持 active, 命令按速率平滑收敛到0; 若命令已到0但 EPS 电机还在出力, 挂起等待卸载
          apply_torque = apply_driver_steer_torque_limits(0, self.apply_torque_last,
                                                          CS.out.steeringTorque, CarControllerParams)
          self.exit_dwell += 1
          if not cmd_settling and eps_loaded:
            print("LOCK4 EXIT-DWELL cmd=0 wait EPS unload: MainTq=%d drvTq=%d dwell=%d" % (
              eps_mt, int(CS.out.steeringTorque), self.exit_dwell))
        else:
          apply_torque = 0
          self.lkas_req_prepare = 0
          self.steerRateLimActive = False
          self.steerRateLim = 1.0
          self.lkas_active = 0
          self.steer_softstart_limit = 0
          self.stall_counter = 0
          self.release_counter = 0
          self.exit_dwell = 0

      self.apply_torque_last = apply_torque
      # LOCK3: 记录本帧 Prepared, 供下帧检测 Prepared 0->1 上升沿 (EPS 请求退出)
      self.eps_prepared_last = bool(CS.lkas_prepared)
      # LOCK5: 记录本帧 lkas_active, 供下帧检测 0->1 重接管沿
      self.lkas_active_last = self.lkas_active

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
        # 速度滞环：防止在目标速度附近频繁点刹震荡
        v_cruise = CS.out.cruiseState.speed  # m/s
        v_ego = CS.out.vEgo
        HYSTERESIS = 0.5  # m/s (约1.8km/h 死区)
        
        # 超速检测：真超速(>v_cruise+HYST)才进入减速态
        if v_ego > v_cruise + HYSTERESIS:
          self.speed_hyst_upper = True
        elif v_ego < v_cruise - HYSTERESIS:
          self.speed_hyst_upper = False
        
        # 在超速区间内抑制过激减速，避免频繁刹车泵启动
        if self.speed_hyst_upper and v_cruise < v_ego < v_cruise + HYSTERESIS * 2:
          # 滞环区间：限制减速度，让自然滑行
          accel = max(accel, -0.3)  # 最多轻减速
        
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
