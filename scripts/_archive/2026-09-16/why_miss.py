# -*- coding: utf-8 -*-
"""침입 미검 편이 왜 안 터졌는지 덤프로 가른다.

가르는 것
  1) 사람이 아예 안 잡혔나 (검출 0)
  2) 잡혔는데 구역 밖인가 (꼭짓점 3개 조건을 못 넘나)
  3) 구역 안인데 신뢰도가 낮나 (conf 0.45 미만)
  4) 다 넘었는데 2표본 연속이 안 됐나 (트랙 ID 가 잘게 끊기나)
"""
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K          # noqa: E402
import kisa_paths as KP         # noqa: E402

CFG = K.ITEMS["intrusion"]
DUMP = V / "dumps/intrusion_tile_v3"


def gt_of(stem):
    g = next(KP.videos("침입").rglob(stem + ".xml"), None)
    a = K.read_alarms(g) if g else []
    return a[0]["start_s"] if a else None


def look(stem):
    rows = [json.loads(l) for l in (DUMP / (stem + ".jsonl")).read_text().splitlines()]
    wh = None
    for r in rows:                       # 프레임 크기는 박스 좌표로 못 구한다. 영역파일 기준 크기를 쓴다
        if r["boxes"]:
            wh = (1280, 720)
            break
    poly = K.zone_of(str(KP.ZONE_MAPS), stem, CFG["zone"], wh or (1280, 720))
    gt = gt_of(stem)

    n_frame = len(rows)
    n_det = n_in = n_conf = 0
    streak = {}
    best_streak = 0
    in_times = []
    for r in rows:
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            n_det += 1
            inside = K.entered((x1, y1, x2, y2), poly, CFG["corners"])
            if not inside:
                continue
            n_in += 1
            if conf < CFG["conf"]:
                continue
            n_conf += 1
            seen.add(pid)
            streak[pid] = streak.get(pid, 0) + 1
            best_streak = max(best_streak, streak[pid])
            in_times.append(r["t"])
        for pid in list(streak):
            if pid not in seen:
                streak[pid] = 0
    # 구역 조건을 꼭짓점 1개로 낮추면 몇 개나 드나 (구역이 좁은지 보려고)
    n_in1 = sum(1 for r in rows for b in r["boxes"]
                if K.entered((b[2], b[3], b[4], b[5]), poly, 1))
    print(f"{stem}  GT {gt}s  프레임 {n_frame}  구역꼭짓점 {poly is not None and len(poly)}")
    print(f"   검출 {n_det}  구역안(3점) {n_in}  구역안(1점) {n_in1}  신뢰도통과 {n_conf}  최장연속 {best_streak} (필요 {CFG['hold']})")
    if in_times:
        print(f"   구역안 시각 {min(in_times):.1f}~{max(in_times):.1f}s")
    # 검출 신뢰도 분포
    cs = sorted((b[1] for r in rows for b in r["boxes"]), reverse=True)
    print(f"   검출 신뢰도 상위: {[round(c,2) for c in cs[:8]]}")
    print()


for s in sys.argv[1:]:
    look(s)
