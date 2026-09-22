# -*- coding: utf-8 -*-
"""배회 오검 편의 트랙 시간표. 덤프만 쓴다.

왜 (2026-09-18)
    손라벨 모델 두 편의 배회 오검 4편은 경보가 정답보다 8~15초 이르거나(211·232·260) 18초 늦다(013).
    영상 시작 물체 문제(warm_s)는 아니었다. 그러면 '어느 트랙이 언제 구역에 들어와서' 경보를 만들었는지
    배포 모델 덤프와 나란히 놓고 봐야 한다. 경보 시각 = 어떤 트랙의 구역 진입 시각 + DELAY(10초) 이므로
    진입 시각이 경보-10초인 트랙이 범인이다.

사용
    python scripts/loiter_fp_timeline.py C00_211_0002 C00_232_0001 ...
"""
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402
import loiter_rule4 as L  # noqa: E402  (sa_now · load 와 같은 판정 경로)

CFG = K.ITEMS["loitering"]
DUMPS = [("배포", "dumps/loiter_botsort_v2"), ("손라벨32.6%", "dumps/loiter_p1280hand_bs1280"), ("손라벨10.8%", "dumps/loiter_p1280ov2_bs1280")]


def tracks_in_zone(rows, poly):
    """구역 안에서 보인 트랙마다 (처음, 마지막, 표본수, 최대 conf, conf>=문턱 표본수)."""
    tr = {}
    for r in rows:
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if not K.entered((x1, y1, x2, y2), poly, CFG["corners"]):
                continue
            d = tr.setdefault(pid, dict(first=r["t"], last=r["t"], n=0, mx=0.0, hi=0))
            d["last"] = r["t"]; d["n"] += 1; d["mx"] = max(d["mx"], conf); d["hi"] += conf >= CFG["conf"]
    return tr


clips = sys.argv[1:] or ["C00_211_0002", "C00_232_0001", "C00_260_0002", "C00_013_0001", "C00_071_0001"]
for stem in clips:
    g = next(KP.videos("배회").rglob(stem + ".xml"), None)
    a = K.read_alarms(g) if g else []
    gt = a[0]["start_s"] if a else None
    print("\n== %s   정답 %s   (경보 창 %s)" % (stem, gt, ("%.1f~%.1f" % (gt - 2, gt + 10)) if gt is not None else "-"))
    for label, d in DUMPS:
        f = Path(d) / (stem + ".jsonl")
        if not f.is_file():
            print("  [%s] 덤프 없음" % label); continue
        rows = [json.loads(l) for l in f.read_text().splitlines()]
        poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], (1280, 720))
        sa = L.sa_now(rows, poly)
        tr = tracks_in_zone(rows, poly)
        mark = "" if sa is None else (" <- 창 안" if gt is not None and gt - 2 <= sa <= gt + 10 else " <- 창 밖(오검)")
        print("  [%s] 경보 %s%s   구역 안 트랙 %d개 (conf %.2f 이상 표본이 있는 것만 표시)" % (
            label, ("%.1fs" % sa) if sa is not None else "없음", mark, len(tr), CFG["conf"]))
        for pid, t in sorted(tr.items(), key=lambda x: x[1]["first"]):
            if t["hi"] == 0:
                continue
            flag = "  <- 진입+10 = 경보" if sa is not None and abs(t["first"] + CFG["delay"] - sa) < 0.26 else ""
            print("      트랙 %4s : %6.1f ~ %6.1fs  표본 %3d (문턱 이상 %3d)  최대 conf %.2f%s" % (
                pid, t["first"], t["last"], t["n"], t["hi"], t["mx"], flag))
