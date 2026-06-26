#!/usr/bin/env python3
from openpilot.tools.lib.logreader import LogReader
import glob
from collections import defaultdict, Counter

pair = defaultdict(Counter)
last_acc = None
for rl in sorted(glob.glob('/data/realdata/00000001--*/rlog.zst')):
    try:
        lr = LogReader(rl)
    except Exception:
        continue
    for m in lr:
        if m.which() == 'can':
            for x in m.can:
                if x.address == 0x32D and x.src == 2:
                    d = bytes(x.dat)
                    if len(d) >= 8:
                        last_acc = (d[2] >> 3) & 0x07
                if x.address == 0x318 and x.src == 0:
                    d = bytes(x.dat)
                    if len(d) >= 8 and last_acc is not None:
                        pair[last_acc][d[0]] += 1

for acc in sorted(pair):
    print(f'AccState={acc}: byte0 -> {pair[acc].most_common(6)}')
