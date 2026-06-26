#!/usr/bin/env python3
from openpilot.tools.lib.logreader import LogReader
import glob, os, sys
from collections import defaultdict

base = sys.argv[1] if len(sys.argv) > 1 else '/data/media/0/realdata'
routes = defaultdict(list)
for seg in sorted(glob.glob(base + '/*/rlog.zst')):
    route = os.path.basename(os.path.dirname(seg)).rsplit('--', 1)[0]
    routes[route].append(seg)

for route, segs in sorted(routes.items()):
    a790 = n790 = p792 = n792 = lat = ncc = 0
    for rl in segs[:3]:
        try:
            lr = LogReader(rl)
        except Exception:
            continue
        for m in lr:
            w = m.which()
            if w == 'carControl':
                ncc += 1
                if m.carControl.latActive:
                    lat += 1
            elif w == 'sendcan':
                for x in m.sendcan:
                    if x.address == 0x316:
                        d = bytes(x.dat)
                        n790 += 1
                        if len(d) >= 4 and (d[3] >> 4) & 1:
                            a790 += 1
            elif w == 'can':
                for x in m.can:
                    if x.address == 0x318 and x.src == 0:
                        d = bytes(x.dat)
                        n792 += 1
                        if len(d) >= 1 and d[0] & 1:
                            p792 += 1
    print(f'{route}: lat={lat}/{ncc} 790act={a790}/{n790} 792prep={p792}/{n792}')
