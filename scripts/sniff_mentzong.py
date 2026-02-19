#!/usr/bin/env python3
"""
嗅探门总 carrotpilot 运行时的 CAN 数据
===========================================
用法:
  1. 在 C3 上安装门总的 carrotpilot 版本
  2. 启动门总版本，让它正常运行
  3. 在另一个 SSH 终端运行此脚本:
     python3 /data/openpilot/scripts/sniff_mentzong.py
  4. 按 ACC 激活横向控制，开车让它控方向盘
  5. 脚本会记录所有 790/792/813/814 消息到 /tmp/mentzong_can.log
  6. 完成后 Ctrl+C 停止

注意: 此脚本通过 cereal 读取数据，需要 openpilot/carrotpilot 正在运行
"""
import time
import sys
from cereal import messaging

sm = messaging.SubMaster(['can'])

logfile = '/tmp/mentzong_can.log'
f = open(logfile, 'w')

def parse_790(dat):
    """Parse ACC_MPC_STATE (790) fields"""
    left_lane = (dat[0] >> 4) & 0x3
    lkas_config = (dat[0] >> 6) & 0x3
    setme2 = dat[1] & 0x3
    req_hands = (dat[1] >> 2) & 1
    mpc_state = (dat[1] >> 3) & 0xF
    lkas_output = (dat[2] | (dat[3] << 8)) & 0x7FF
    if lkas_output > 1023:
        lkas_output -= 2048
    lkas_reqprepare = (dat[3] >> 3) & 1
    lkas_active = (dat[3] >> 4) & 1
    right_lane = (dat[4] >> 2) & 0x3
    lkas_state = (dat[4] >> 4) & 0xF
    counter = (dat[6] >> 4) & 0xF
    checksum = dat[7]
    return (f"Out={lkas_output:4d} Act={lkas_active} ReqP={lkas_reqprepare} "
            f"MPC_St={mpc_state} LKAS_St={lkas_state} Cfg={lkas_config} "
            f"ReqHands={req_hands} LL={left_lane} RL={right_lane} "
            f"cnt={counter} chk={checksum:02x}")

def parse_792(dat):
    """Parse ACC_EPS_STATE (792) fields"""
    prepared = dat[0] & 1
    cruise_act = (dat[0] >> 1) & 1
    torque_failed = (dat[0] >> 2) & 1
    steer_warning = (dat[0] >> 4) & 1
    steer_error = (dat[0] >> 5) & 0x7
    main_torque = (dat[1] | (dat[2] << 8)) & 0xFFF
    if main_torque > 2047:
        main_torque -= 4096
    hands_off = (dat[2] >> 5) & 1
    driver_torque = ((dat[3] | (dat[4] << 8)) & 0xFFF)
    if driver_torque > 2047:
        driver_torque -= 4096
    counter = (dat[6] >> 4) & 0xF
    checksum = dat[7]
    return (f"MainTrq={main_torque:4d} Prep={prepared} CruAct={cruise_act} "
            f"TrqFail={torque_failed} StWarn={steer_warning} StErr={steer_error} "
            f"HandsOff={hands_off} DrvTrq={driver_torque:4d} cnt={counter} chk={checksum:02x}")

def parse_813(dat):
    """Parse ACC_HUD_ADAS (813) fields"""
    set_speed = (dat[0] | ((dat[1] & 0x1) << 8)) * 0.5
    has_lead = (dat[1] >> 1) & 1
    set_dist = (dat[1] >> 2) & 0x7
    acc_state = (dat[2] >> 3) & 0x7
    acc_on1 = (dat[2] >> 6) & 1
    counter = (dat[6] >> 0) & 0xF
    return (f"SetSpd={set_speed:5.1f} HasLead={has_lead} SetDist={set_dist} "
            f"AccState={acc_state} AccOn1={acc_on1} cnt={counter}")

print(f"嗅探门总 CAN 数据，写入 {logfile}")
print("按 ACC 激活横向控制，开车测试")
print("按 Ctrl+C 停止\n")

f.write("# 门总 carrotpilot CAN 嗅探数据\n")
f.write(f"# 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
f.write("# bus: 0=Bus0(EPS/ESC), 2=Bus2(MPC), 128=TX(OP发送到Bus0), 130=TX(OP发送到Bus2)\n\n")

count = 0
t0 = time.monotonic()

try:
    while True:
        sm.update(200)
        if not sm.updated['can']:
            continue

        t = time.monotonic() - t0

        for msg in sm['can']:
            addr = msg.address
            bus = msg.src
            dat = bytes(msg.dat)

            # 790 ACC_MPC_STATE
            if addr == 0x316:
                parsed = parse_790(dat)
                bus_label = {0: "RX_Bus0", 2: "RX_Bus2", 128: "TX_Bus0", 130: "TX_Bus2"}.get(bus, f"bus{bus}")
                line = f"[{t:8.3f}] 790 {bus_label:8s} {parsed} raw={dat.hex()}"
                f.write(line + "\n")
                if count % 3 == 0:
                    print(line)
                count += 1

            # 792 ACC_EPS_STATE
            elif addr == 0x318:
                parsed = parse_792(dat)
                bus_label = {0: "RX_Bus0", 2: "RX_Bus2", 128: "TX_Bus0", 130: "TX_Bus2"}.get(bus, f"bus{bus}")
                line = f"[{t:8.3f}] 792 {bus_label:8s} {parsed} raw={dat.hex()}"
                f.write(line + "\n")
                # Only print 792 when MainTorque changes or Prepared changes
                if "MainTrq=   0" not in parsed or "Prep=1" in parsed:
                    print(line)

            # 813 ACC_HUD_ADAS
            elif addr == 0x32D:
                parsed = parse_813(dat)
                bus_label = {0: "RX_Bus0", 2: "RX_Bus2", 128: "TX_Bus0", 130: "TX_Bus2"}.get(bus, f"bus{bus}")
                line = f"[{t:8.3f}] 813 {bus_label:8s} {parsed} raw={dat.hex()}"
                f.write(line + "\n")

except KeyboardInterrupt:
    pass

f.write(f"\n# 结束时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
f.write(f"# 总消息数: {count}\n")
f.close()

print(f"\n\n完成！共记录 {count} 条消息")
print(f"数据保存在: {logfile}")
print(f"查看: cat {logfile}")
print(f"只看 790 TX: grep 'TX_Bus0' {logfile} | grep '790' | head -50")
print(f"只看 792 有扭矩: grep '792' {logfile} | grep -v 'MainTrq=   0' | head -50")
