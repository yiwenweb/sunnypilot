#!/usr/bin/env python3
"""
从rlog直接提取速度系数
适配C3上的数据：00000006--e894677787 (你自己的录制)
需要在C3上运行（有LogReader）

运行方法：
  cd /data/openpilot && source /usr/local/venv/bin/activate && export PYTHONPATH=/data/openpilot
  python /data/byd_speed_from_rlog.py
"""
import sys
import glob
import numpy as np

def analyze_route(route_pattern):
    """分析一个route的速度"""
    segments = sorted(glob.glob(route_pattern))
    
    if not segments:
        print(f"未找到route，检查路径: {route_pattern}")
        return None
    
    print(f"找到 {len(segments)} 段")
    
    # 需要在C3上运行才能导入
    from openpilot.tools.lib.logreader import LogReader
    
    # 收集 (raw_speed, vEgo_真值) 配对
    pairs = []
    
    for seg_dir in segments[:15]:  # 前15段够用
        rlog_path = seg_dir + '/rlog'
        print(f"读取 {seg_dir.split('/')[-1]}...")
        
        try:
            for msg in LogReader(rlog_path):
                if msg.which() == 'can':
                    # 找 0x121(289) CARSPEED
                    for can_msg in msg.can:
                        if can_msg.address == 289 and can_msg.src == 0:  # bus0
                            dat = bytes(can_msg.dat)
                            if len(dat) >= 2:
                                # 12-bit unsigned, little-endian
                                raw_speed = dat[0] | ((dat[1] & 0x0F) << 8)
                                if raw_speed > 0:
                                    # 记录时间戳，待与carState对齐
                                    pairs.append(('can', msg.logMonoTime, raw_speed))
                
                elif msg.which() == 'carState':
                    cs = msg.carState
                    vEgo_ms = cs.vEgo
                    vEgo_kph = vEgo_ms * 3.6
                    if vEgo_kph > 5:  # 只要动起来的
                        pairs.append(('cs', msg.logMonoTime, vEgo_kph))
        
        except Exception as e:
            print(f"  错误: {e}")
            continue
    
    # 按时间排序
    pairs.sort(key=lambda x: x[1])
    
    # 时间对齐：每个carState找最近的CAN
    can_data = [(t, val) for typ, t, val in pairs if typ == 'can']
    cs_data = [(t, val) for typ, t, val in pairs if typ == 'cs']
    
    print(f"CAN样本: {len(can_data)}, carState样本: {len(cs_data)}")
    
    aligned = []
    for t_cs, vEgo_kph in cs_data:
        # 找最近的CAN时间戳
        closest = min(can_data, key=lambda x: abs(x[0] - t_cs))
        if abs(closest[0] - t_cs) < 50_000_000:  # 50ms内
            raw_speed = closest[1]
            aligned.append((raw_speed, vEgo_kph))
    
    print(f"对齐配对: {len(aligned)} 组")
    
    if not aligned:
        return None
    
    # 计算系数 K = vEgo_kph / raw_speed
    scales = [vEgo / raw for raw, vEgo in aligned if raw > 0]
    
    median_scale = np.median(scales)
    mean_scale = np.mean(scales)
    
    print(f"\n实测系数:")
    print(f"  中位数: {median_scale:.5f}")
    print(f"  均值:   {mean_scale:.5f}")
    print(f"\n当前代码: 0.0735")
    print(f"实测值: {median_scale:.5f}")
    print(f"差异: {(median_scale - 0.0735) / 0.0735 * 100:+.2f}%")
    
    # 分速度段检查线性
    print("\n分速度段:")
    for low, high in [(0, 40), (40, 70), (70, 100), (100, 150)]:
        samples = [(r, v) for r, v in aligned if low < v < high]
        if len(samples) > 10:
            s = [v/r for r, v in samples]
            print(f"  {low:3d}-{high:3d}km/h: {np.median(s):.5f} ({len(samples)}样本)")
    
    return median_scale

if __name__ == '__main__':
    print("=" * 80)
    print("速度系数分析（从rlog）")
    print("=" * 80)
    
    # 分析你自己的录制数据（00000006）
    route_path = '/data/realdata/realdata/00000006--e894677787--*'
    
    scale = analyze_route(route_path)
    
    if scale:
        print("\n" + "=" * 80)
        print(f"建议修改: K_DASHSPEED = {scale:.5f}")
        print("=" * 80)
    else:
        print("\n未成功分析，检查数据路径或格式")
