# -*- coding: utf-8 -*-
"""SAM 전파 저장소 요약: 클립별 프레임 수 · 객체별 박스 수 · 갱신 시각. 최근 갱신 순."""
import json, io, glob, os, collections, sys
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
fs = sorted(glob.glob(f"{V}/data/학습데이터/자동라벨/sam2/*.json"), key=os.path.getmtime, reverse=True)[:n]
for f in fs:
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except Exception as e:
        print(os.path.basename(f), "읽기 실패", e); continue
    fr = d.get("frames") or {}
    c = collections.Counter()
    for v in fr.values():
        for o in v:
            c[o] += 1
    seeds = collections.Counter(str(s.get("obj")) for s in (d.get("seeds") or []))
    print(f"{d.get('clip', os.path.basename(f)):22s} 프레임 {len([1 for v in fr.values() if v]):4d} "
          f"결과 {dict(sorted(c.items()))} 씨앗 {dict(sorted(seeds.items()))} {d.get('updated', '')}")
