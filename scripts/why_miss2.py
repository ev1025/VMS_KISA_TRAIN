# -*- coding: utf-8 -*-
"""침입 미검 편: 구역 안 박스의 신뢰도와 시각을 그대로 본다."""
import json
import sys
from pathlib import Path

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K          # noqa: E402
import kisa_paths as KP         # noqa: E402

CFG = K.ITEMS["intrusion"]
DUMP = V / "dumps/intrusion_tile_v3"


def look(stem):
    rows = [json.loads(l) for l in (DUMP / (stem + ".jsonl")).read_text().splitlines()]
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
    g = next(KP.videos("침입").rglob(stem + ".xml"), None)
    gt = (K.read_alarms(g) or [{}])[0].get("start_s")

    foot = []      # 발끝만 통과
    full = []      # 발끝 + 꼭짓점 3개
    for r in rows:
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if K.entered((x1, y1, x2, y2), poly, 0):
                foot.append((r["t"], pid, conf))
            if K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                full.append((r["t"], pid, conf))

    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    print(f"== {stem}  GT {gt}s  구역 x{min(xs)}~{max(xs)} y{min(ys)}~{max(ys)}  (문턱 {CFG['conf']})")
    for name, lst in (("발끝만", foot), ("몸전체", full)):
        if not lst:
            print(f"   {name}: 0건"); continue
        cs = sorted(c for _, _, c in lst)
        ok = [x for x in lst if x[2] >= CFG["conf"]]
        print(f"   {name}: {len(lst)}건  신뢰도 최소 {cs[0]:.2f} 중앙 {cs[len(cs)//2]:.2f} 최대 {cs[-1]:.2f}"
              f"  문턱통과 {len(ok)}건")
        print(f"      시각 {min(t for t,_,_ in lst):.1f}~{max(t for t,_,_ in lst):.1f}s"
              f"  GT 근처(±15s) {sum(1 for t,_,_ in lst if gt and abs(t-gt)<=15)}건")
        near = [(t, p, round(c, 2)) for t, p, c in lst if gt and abs(t - gt) <= 15][:10]
        if near:
            print(f"      GT 근처 표본: {near}")
    print()


for s in sys.argv[1:]:
    look(s)
