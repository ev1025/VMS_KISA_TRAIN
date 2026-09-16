# -*- coding: utf-8 -*-
"""침입: 신뢰도 문턱(과 hold)을 낮추면 미검 3편이 살아나는지 덤프 30편으로 확인한다.

덤프는 dumps/intrusion_tile_v3 (제출 실측 94.74 를 그대로 재현하는 덤프).
규칙은 제출 도구의 IntrusionRule 을 그대로 쓴다(복사하지 않는다).
"""
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
CLIPS = sorted(p.stem for p in DUMP.glob("*.jsonl"))

GT = {}
for s in CLIPS:
    g = next(KP.videos("침입").rglob(s + ".xml"), None)
    a = K.read_alarms(g) if g else []
    GT[s] = a[0]["start_s"] if a else None

ROWS = {s: [json.loads(l) for l in (DUMP / (s + ".jsonl")).read_text().splitlines()] for s in CLIPS}
POLY = {s: K.zone_of(str(KP.ZONE_MAPS), s, CFG["zone"], (1280, 720)) for s in CLIPS}


def run(conf, hold, corners):
    pairs, detail = [], {}
    for s in CLIPS:
        j = K.IntrusionRule(POLY[s], conf, corners, hold, CFG["settle"], CFG["gap"])
        for r in ROWS[s]:
            j.feed(r["t"], r["boxes"])
        sa = j.final()
        detail[s] = sa
        gts = [{"start_s": GT[s], "desc": "Intrusion"}] if GT[s] is not None else []
        sas = [{"start_s": sa, "desc": "Intrusion"}] if sa is not None else []
        pairs.append((gts, sas))
    return K.score(pairs), detail


BASE, BD = run(CFG["conf"], CFG["hold"], CFG["corners"])
print(f"현재 conf={CFG['conf']} hold={CFG['hold']} corners={CFG['corners']}"
      f" -> {BASE['점수']:.2f} (정검 {BASE['정상검출']} 미검 {BASE['미검출']} 오검 {BASE['오검출']})")
WATCH = ("C00_249_0003", "C00_255_0001", "C00_275_0001")
print()
print("conf  hold corners  점수    정검 미검 오검   미검3편 SA (GT 111 / 137 / 134)")
for corners in (3, 1):
    for hold in (2, 1):
        for conf in (0.45, 0.40, 0.35, 0.30, 0.25, 0.20, 0.15, 0.10):
            s, d = run(conf, hold, corners)
            w = " ".join("-" if d[c] is None else f"{d[c]:.0f}" for c in WATCH)
            mark = "  <= 지금" if (conf, hold, corners) == (CFG["conf"], CFG["hold"], CFG["corners"]) else ""
            print(f"{conf:4.2f}  {hold}    {corners}     {s['점수']:6.2f}  {s['정상검출']:3d} {s['미검출']:3d} {s['오검출']:3d}"
                  f"    {w}{mark}")
        print()
