#!/usr/bin/env python3
"""
BYD CANPacker 输出验证工具

验证 CANPacker 编码的帧是否与原厂 MPC 嗅探数据一致。
不需要连接车辆，在任何环境下都可以运行。

原厂 MPC 嗅探数据 (diag_switch_moment.py 确认):
  790 stock idle:   c2 81 00 40 71 00 Cx xx  (LKAS_Config=3, AutoFullBeamState=2, LKAS_State=7)
  813 ACC active:   00 00 7c 4d f7 ff Fx xx  (AccState=7, AccOn1=1, Status=7, Notify=38)
  814 ACC idle:     64 64 64 80 50 40 Fx xx  (AccelCmd=0, EspBehaviour=1)
  815 stock idle:   05 80 02 0f ff ff Fx xx
  792 EPS normal:   fc 00 f0 00 ff ff Cx xx  (TorqueFailed=1, SteerWarning=1, SteerErrorCode=7)

使用方法:
  python3 diag_canpacker_verify.py
"""

import sys
import os

# 添加 opendbc 路径
script_dir = os.path.dirname(os.path.abspath(__file__))
opendbc_root = os.path.join(script_dir, "..")
sys.path.insert(0, opendbc_root)

from opendbc.can import CANPacker

DBC_FILE = "byd_tang_dm_2018"

def hex_str(data):
    return " ".join(f"{b:02x}" for b in data)

def byd_checksum(dat):
    return (0xFF - sum(dat[:7])) & 0xFF

def chk_ok(data):
    return sum(data[:8]) & 0xFF == 0xFF

def verify_790():
    """验证 790 ACC_MPC_STATE 空闲帧"""
    print("=" * 60)
    print("790 ACC_MPC_STATE (LKAS 控制)")
    print("=" * 60)

    packer = CANPacker(DBC_FILE)

    # 原厂空闲值
    values = {
        "AutoFullBeamState": 2,
        "LeftLaneState": 0,
        "LKAS_Config": 3,
        "SETME2_0x1": 1,
        "ReqHandsOnSteeringWheel": 0,
        "MPC_State": 0,
        "AutoFullBeam_OnOff": 1,
        "LKAS_Output": 0,
        "LKAS_ReqPrepare": 0,
        "LKAS_Active": 0,
        "SETME3_0x0": 0,
        "TrafficSignRecognition_OnOff": 1,
        "SETME4_0x0": 0,
        "SETME5_0x1": 1,
        "RightLaneState": 0,
        "LKAS_State": 7,
        "TrafficSignRecognition_Result": 0,
        "LKAS_AlarmType": 0,
        "SETME7_0x3": 3,
        "COUNTER": 0,
        "CHECKSUM": 0,
    }

    msg = packer.make_can_msg("ACC_MPC_STATE", 0, values)
    dat = bytearray(msg[1])
    dat[7] = byd_checksum(dat)

    # 原厂: c2 81 00 40 71 00 0x xx (counter=0)
    stock = bytearray([0xc2, 0x81, 0x00, 0x40, 0x71, 0x00, 0x00, 0x00])
    stock[6] = (0 << 4) | 0x03  # counter=0 in high nibble, SETME7=3 in... wait
    # 790 counter is at bits 52-55 (high nibble of byte[6])
    # LKAS_AlarmType at bits 49-50, SETME7 at bits 51-52... let me check
    # Actually byte[6] = counter(high nibble) | AlarmType+SETME7(low nibble)
    # Stock: Cx → counter=C=12, low nibble=x varies
    # For counter=0: byte[6] should have counter=0 in high nibble
    # Low nibble: AlarmType=0 (2 bits), SETME7=3 (2 bits) → 0b0011 = 0x3
    stock[6] = (0 << 4) | 0x03  # counter=0, AlarmType=0, SETME7=3
    stock[7] = byd_checksum(stock)

    print(f"  CANPacker: {hex_str(dat)}  CHK={'✓' if chk_ok(dat) else '✗'}")
    print(f"  Expected:  {hex_str(stock)}  CHK={'✓' if chk_ok(stock) else '✗'}")

    match = dat[:6] == stock[:6]
    print(f"  Data match (byte 0-5): {'✓ 一致' if match else '✗ 不一致'}")
    if not match:
        for i in range(6):
            if dat[i] != stock[i]:
                print(f"    byte[{i}]: got 0x{dat[i]:02X}, expected 0x{stock[i]:02X}")
                print(f"             got bits: {dat[i]:08b}")
                print(f"             exp bits: {stock[i]:08b}")

    # 验证 counter 位置
    for cnt in range(16):
        values["COUNTER"] = cnt
        values["CHECKSUM"] = 0
        m = packer.make_can_msg("ACC_MPC_STATE", 0, values)
        d = bytearray(m[1])
        print(f"  counter={cnt:2d}: byte[6]=0x{d[6]:02X} ({d[6]:08b})", end="")
        expected_b6 = (cnt << 4) | 0x03  # counter in high nibble
        print(f"  expected=0x{expected_b6:02X} ({expected_b6:08b})", end="")
        print(f"  {'✓' if d[6] == expected_b6 else '✗ MISMATCH'}")

    print()


def verify_813():
    """验证 813 ACC_HUD_ADAS ACC激活帧"""
    print("=" * 60)
    print("813 ACC_HUD_ADAS (ACC HUD)")
    print("=" * 60)

    packer = CANPacker(DBC_FILE)

    # ACC 激活值 (匹配原厂)
    values = {
        "SetSpeed": 0,
        "HasLead": 0,
        "SetDistance": 4,
        "LeadingDistance": 0,
        "AEB": 0,
        "FCW": 0,
        "SETME1_0x1": 1,
        "AccState": 7,
        "AccOn1": 1,
        "CloseWarning": 0,
        "SETME2_0x1": 1,
        "Notify": 38,
        "Status": 7,
        "SETME3_0xFFF": 0xFFF,
        "COUNTER": 0,
        "SETME4_0xF": 0xF,
        "CHECKSUM": 0,
    }

    msg = packer.make_can_msg("ACC_HUD_ADAS", 0, values)
    dat = bytearray(msg[1])
    dat[7] = byd_checksum(dat)

    # 原厂 ACC 激活: 00 00 7c 4d f7 ff Fx xx
    # SetSpeed=0 → byte[0:1] = 00 00
    # byte[2] = 0x7C = 0111 1100
    #   SetDistance=4 (bits 10-12) → 100 at bits 2-4 of byte[1]... hmm
    #   Actually SetDistance is at bits 10-12 which spans byte[1] bits 2-4
    #   Let me just compare raw bytes
    stock = bytearray([0x00, 0x00, 0x7c, 0x4d, 0xf7, 0xff, 0x00, 0x00])
    # counter=0 for comparison
    # 813 counter is in LOW nibble of byte[6] (bits 48-51)
    # SETME4_0xF is in HIGH nibble of byte[6] (bits 55-52, Motorola)
    stock[6] = (0xF << 4) | 0  # SETME4=F, counter=0
    stock[7] = byd_checksum(stock)

    print(f"  CANPacker: {hex_str(dat)}  CHK={'✓' if chk_ok(dat) else '✗'}")
    print(f"  Expected:  {hex_str(stock)}  CHK={'✓' if chk_ok(stock) else '✗'}")

    match = dat[:6] == stock[:6]
    print(f"  Data match (byte 0-5): {'✓ 一致' if match else '✗ 不一致'}")
    if not match:
        for i in range(6):
            if dat[i] != stock[i]:
                print(f"    byte[{i}]: got 0x{dat[i]:02X} ({dat[i]:08b}), expected 0x{stock[i]:02X} ({stock[i]:08b})")

    # 验证 counter 位置
    for cnt in [0, 1, 5, 15]:
        values["COUNTER"] = cnt
        values["CHECKSUM"] = 0
        m = packer.make_can_msg("ACC_HUD_ADAS", 0, values)
        d = bytearray(m[1])
        expected_b6 = (0xF << 4) | (cnt & 0xF)
        print(f"  counter={cnt:2d}: byte[6]=0x{d[6]:02X}  expected=0x{expected_b6:02X}  {'✓' if d[6] == expected_b6 else '✗'}")

    # 也测试 SetSpeed 不为 0 的情况
    values["SetSpeed"] = 60  # 60 km/h
    values["COUNTER"] = 0
    values["CHECKSUM"] = 0
    msg = packer.make_can_msg("ACC_HUD_ADAS", 0, values)
    dat = bytearray(msg[1])
    dat[7] = byd_checksum(dat)
    print(f"  SetSpeed=60: {hex_str(dat)}")
    # SetSpeed=60, scale=0.5 → raw=120=0x78, 9-bit → byte[0]=0x78, byte[1] bit0=0
    print(f"    byte[0]=0x{dat[0]:02X} (expected 0x78 for raw=120)")

    print()


def verify_814():
    """验证 814 ACC_CMD 空闲帧"""
    print("=" * 60)
    print("814 ACC_CMD (ACC 加速度指令)")
    print("=" * 60)

    packer = CANPacker(DBC_FILE)

    # 空闲值 (AccelCmd=0 物理值)
    values = {
        "AccelCmd": 0,
        "ComfortBandUpper": 0,
        "ComfortBandLower": 0,
        "JerkUpperLimit": 0,
        "SETME1_0x1": 1,
        "JerkLowerLimit": 0,
        "ResumeFromStandstill": 0,
        "StandstillState": 0,
        "BrakeBehaviour": 0,
        "AccReqNotStandstill": 0,
        "AccControlActive": 0,
        "AccOverrideOrStandstill": 0,
        "EspBehaviour": 1,
        "COUNTER": 0,
        "SETME2_0xF": 0xF,
        "CHECKSUM": 0,
    }

    msg = packer.make_can_msg("ACC_CMD", 0, values)
    dat = bytearray(msg[1])
    dat[7] = byd_checksum(dat)

    # 原厂空闲: 64 64 64 80 50 40 Fx xx
    # AccelCmd=0 → raw=(0-(-5))/0.05=100=0x64 ✓
    # ComfortBandUpper=0 → raw=100=0x64 ✓
    # ComfortBandLower=0 → raw=100=0x64 ✓
    # JerkUpperLimit=0 → raw=0/0.2=0 → byte[3] bits 0-6 = 0
    # SETME1=1 → byte[3] bit 7 = 1 → byte[3] = 0x80 ✓
    # JerkLowerLimit=0 → raw=(0-(-16))/0.2=80=0x50 → byte[4] bits 0-6 = 0x50 ✓
    # EspBehaviour=1 → bits 46-47 → byte[5] bits 6-7 = 01 → 0x40 ✓
    stock = bytearray([0x64, 0x64, 0x64, 0x80, 0x50, 0x40, 0x00, 0x00])
    stock[6] = (0xF << 4) | 0  # SETME2=F, counter=0
    stock[7] = byd_checksum(stock)

    print(f"  CANPacker: {hex_str(dat)}  CHK={'✓' if chk_ok(dat) else '✗'}")
    print(f"  Expected:  {hex_str(stock)}  CHK={'✓' if chk_ok(stock) else '✗'}")

    match = dat[:6] == stock[:6]
    print(f"  Data match (byte 0-5): {'✓ 一致' if match else '✗ 不一致'}")
    if not match:
        for i in range(6):
            if dat[i] != stock[i]:
                print(f"    byte[{i}]: got 0x{dat[i]:02X} ({dat[i]:08b}), expected 0x{stock[i]:02X} ({stock[i]:08b})")

    print()


def verify_815():
    """验证 815 ACC_AEB 空闲帧 (手动构建)"""
    print("=" * 60)
    print("815 ACC_AEB (AEB 控制) — 手动构建")
    print("=" * 60)

    # 手动构建 (carcontroller.py 中的 _create_acc_aeb)
    dat = bytearray([0x05, 0x80, 0x02, 0x0f, 0xff, 0xff, 0x00, 0x00])
    dat[6] = (0xF << 4) | 0  # SETME=F, counter=0
    dat[7] = byd_checksum(dat)

    stock = bytearray([0x05, 0x80, 0x02, 0x0f, 0xff, 0xff, 0x00, 0x00])
    stock[6] = (0xF << 4) | 0
    stock[7] = byd_checksum(stock)

    print(f"  Manual:   {hex_str(dat)}  CHK={'✓' if chk_ok(dat) else '✗'}")
    print(f"  Expected: {hex_str(stock)}  CHK={'✓' if chk_ok(stock) else '✗'}")
    print(f"  Match: {'✓ 一致' if dat == stock else '✗ 不一致'}")
    print()


def verify_792():
    """验证 792 ACC_EPS_STATE 假反馈帧"""
    print("=" * 60)
    print("792 ACC_EPS_STATE (假 EPS 反馈)")
    print("=" * 60)

    packer = CANPacker(DBC_FILE)

    # 空闲值 (匹配原厂 EPS)
    values = {
        "LKAS_Prepared": 0,
        "CruiseActivated": 0,
        "TorqueFailed": 1,
        "SETME1_0x1": 1,
        "SteerWarning": 1,
        "SteerErrorCode": 7,
        "MainTorque": 0,
        "SETME3_0x1": 1,
        "ReportHandsNotOnSteeringWheel": 1,
        "SETME4_0x3": 3,
        "SteerDriverTorque": 0,
        "SETME5_0xFF": 0xF,
        "SETME6_0xFFF": 0xFFF,
    }

    msg = packer.make_can_msg("ACC_EPS_STATE", 2, values)
    dat = bytearray(msg[1])
    # 手动填充 counter 和 checksum
    dat[6] = (0 << 4) | 0xF  # counter=0 in high nibble, SETME=F in low nibble
    dat[7] = byd_checksum(dat)

    # 原厂: fc 00 f0 00 ff ff Cx xx (counter varies)
    # byte[0] = 0xFC = 1111 1100
    #   bit0=LKAS_Prepared=0, bit1=CruiseActivated=0, bit2=TorqueFailed=1,
    #   bit3=SETME1=1, bit4=SteerWarning=1, bit5-7=SteerErrorCode=7(111)
    #   → 0b11111100 = 0xFC ✓
    # byte[1] = 0x00 (MainTorque low byte = 0)
    # byte[2] = 0xF0
    #   MainTorque high nibble (bits 8-11 of MainTorque=0 → bits 0-3 of byte[1]=0)
    #   Wait, MainTorque is 12-bit at bit 8. So bits 8-19.
    #   byte[1] = MainTorque bits 0-7 = 0x00
    #   byte[2] bits 0-3 = MainTorque bits 8-11 = 0
    #   byte[2] bit 4 = SETME3_0x1 = 1
    #   byte[2] bit 5 = ReportHandsNotOnSteeringWheel = 1
    #   byte[2] bits 6-7 = SETME4_0x3 = 3 (11)
    #   → byte[2] = 0b11110000 = 0xF0 ✓
    stock = bytearray([0xfc, 0x00, 0xf0, 0x00, 0xff, 0xff, 0x00, 0x00])
    stock[6] = (0 << 4) | 0xF  # counter=0, SETME=F
    stock[7] = byd_checksum(stock)

    print(f"  CANPacker: {hex_str(dat)}  CHK={'✓' if chk_ok(dat) else '✗'}")
    print(f"  Expected:  {hex_str(stock)}  CHK={'✓' if chk_ok(stock) else '✗'}")

    match = dat[:6] == stock[:6]
    print(f"  Data match (byte 0-5): {'✓ 一致' if match else '✗ 不一致'}")
    if not match:
        for i in range(6):
            if dat[i] != stock[i]:
                print(f"    byte[{i}]: got 0x{dat[i]:02X} ({dat[i]:08b}), expected 0x{stock[i]:02X} ({stock[i]:08b})")

    # 也测试 LKAS 激活状态
    values["CruiseActivated"] = 1
    values["MainTorque"] = 50
    msg = packer.make_can_msg("ACC_EPS_STATE", 2, values)
    dat2 = bytearray(msg[1])
    dat2[6] = (1 << 4) | 0xF
    dat2[7] = byd_checksum(dat2)
    print(f"  LKAS active (torque=50): {hex_str(dat2)}")
    print(f"    byte[0]=0x{dat2[0]:02X} (expected 0xFE: CruiseActivated=1)")

    # byte[4] = SETME5_0xFF at bits 36-39 (4 bits)
    # SETME6_0xFFF at bits 40-51 (12 bits)
    # byte[4] bits 0-3 = SETME5 = 0xF
    # byte[4] bits 4-7 = SETME6 low 4 bits = 0xF
    # → byte[4] = 0xFF ✓
    # byte[5] = SETME6 bits 4-11 = 0xFF ✓

    print()


def verify_813_with_setspeed():
    """验证 813 在 carcontroller 实际调用方式下的输出"""
    print("=" * 60)
    print("813 ACC_HUD_ADAS — 模拟 carcontroller 调用")
    print("=" * 60)

    # 模拟 carcontroller 中的实际调用
    # hud_set_speed = CS.out.vEgoCluster * 3.6 (假设 0 km/h)
    # create_acc_hud(packer, CP, CS, set_speed=0, has_lead=False, set_distance=4,
    #               acc_state=7, enabled=True, counter=0)

    packer = CANPacker(DBC_FILE)

    # enabled=True 时的值
    values = {
        "SetSpeed": 0,  # 0 km/h
        "HasLead": 0,
        "SetDistance": 4,
        "LeadingDistance": 0,
        "AEB": 0,
        "FCW": 0,
        "SETME1_0x1": 1,
        "AccState": 7,
        "AccOn1": 1,
        "CloseWarning": 0,
        "SETME2_0x1": 1,
        "Notify": 38,
        "Status": 7,
        "SETME3_0xFFF": 0xFFF,
        "COUNTER": 0,
        "SETME4_0xF": 0xF,
        "CHECKSUM": 0,
    }

    # 第一次 make_can_msg (计算 checksum 前)
    msg1 = packer.make_can_msg("ACC_HUD_ADAS", 0, values)
    dat1 = bytearray(msg1[1])
    print(f"  Before checksum: {hex_str(dat1)}")

    # 计算 checksum
    values["CHECKSUM"] = byd_checksum(dat1)

    # 第二次 make_can_msg (带 checksum)
    msg2 = packer.make_can_msg("ACC_HUD_ADAS", 0, values)
    dat2 = bytearray(msg2[1])
    print(f"  After checksum:  {hex_str(dat2)}  CHK={'✓' if chk_ok(dat2) else '✗'}")

    # 原厂参考
    stock = bytearray([0x00, 0x00, 0x7c, 0x4d, 0xf7, 0xff, 0xf0, 0x00])
    stock[7] = byd_checksum(stock)
    print(f"  Stock reference:  {hex_str(stock)}  CHK={'✓' if chk_ok(stock) else '✗'}")

    # 逐字节对比
    for i in range(8):
        marker = "  " if dat2[i] == stock[i] else "**"
        print(f"  {marker} byte[{i}]: ours=0x{dat2[i]:02X} ({dat2[i]:08b})  stock=0x{stock[i]:02X} ({stock[i]:08b})")

    print()


if __name__ == "__main__":
    print("BYD CANPacker 输出验证")
    print("验证 CANPacker 编码是否与原厂 MPC 嗅探数据一致")
    print()

    verify_790()
    verify_813()
    verify_813_with_setspeed()
    verify_814()
    verify_815()
    verify_792()

    print("=" * 60)
    print("验证完成")
    print("如果有 ✗ 标记，说明 CANPacker 输出与原厂不一致")
    print("需要检查 DBC 信号定义（特别是 Motorola/Intel 字节序）")
    print("=" * 60)
