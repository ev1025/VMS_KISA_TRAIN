# -*- coding: utf-8 -*-
"""배회 미검 편이 왜 안 터졌나. 침입과 같은 4단계로 가른다.
   1 사람이 검출됐나  2 구역 밖인가  3 신뢰도가 낮나  4 체류를 못 채웠나"""
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["loitering"]
D = V / "dumps/loiter_botsort_v2"


def look(stem):
    rows = [json.loads(l) for l in (D / (stem + ".jsonl")).read_text().splitlines()]
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
    g = next(KP.videos("배회").rglob(stem + ".xml"), None)
    gt = (K.read_alarms(g) or [{}])[0].get("start_s")

    n_det = n_in = n_conf = 0
    dwell = {}
    best_dwell = 0.0
    times, confs, ids = [], [], set()
    for r in rows:
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            n_det += 1
            if not K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                continue
            n_in += 1
            confs.append(conf)
            if conf < CFG["conf"]:
                continue
            n_conf += 1
            seen.add(pid); ids.add(pid); times.append(r["t"])
            dwell[pid] = dwell.get(pid, 0) + CFG["stride"]
            best_dwell = max(best_dwell, dwell[pid])
        for pid in list(dwell):
            if pid not in seen:
                dwell[pid] = 0
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    print(f"== {stem}  GT {gt}s  구역 {max(xs)-min(xs)}x{max(ys)-min(ys)}px  (문턱 {CFG['conf']} · 체류 {CFG['dwell']}초)")
    print(f"   검출 {n_det}  구역안 {n_in}  문턱통과 {n_conf}  최장체류 {best_dwell:.1f}초  트랙 {len(ids)}개")
    if confs:
        confs.sort()
        print(f"   구역안 신뢰도  최소 {confs[0]:.2f} 중앙 {confs[len(confs)//2]:.2f} 최대 {confs[-1]:.2f}")
    if times:
        print(f"   구역안 시각 {min(times):.1f}~{max(times):.1f}s · GT 근처(±20s) {sum(1 for t in times if gt and abs(t-gt)<=20)}표본")
    hs = sorted(y2 - y1 for r in rows for _, c, x1, y1, x2, y2 in r["boxes"]
                if K.entered((x1, y1, x2, y2), poly, CFG["corners"]))
    if hs:
        print(f"   구역안 사람 키 {hs[0]:.0f}~{hs[-1]:.0f}px (중앙 {hs[len(hs)//2]:.0f})")
    print()


for s in sys.argv[1:] or ["C00_115_0001", "C00_225_0001"]:
    look(s)
