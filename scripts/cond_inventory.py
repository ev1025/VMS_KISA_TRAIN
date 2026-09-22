# -*- coding: utf-8 -*-
"""KISA 영상(채점셋·연구개발)의 촬영 조건 분포와, 손라벨이 조건별로 얼마나 붙어 있는지 센다. 읽기만 한다.

왜 (2026-09-19)
    실패 편이 야간·눈·새벽에 몰려 있다. 그 조건의 영상이 원본에 얼마나 있고, 그중 얼마를 이미 라벨했는지 알아야
    '무엇을 더 가져와야 하나 / 무엇을 더 찍어야 하나' 를 말할 수 있다.

읽는 곳
    정답 xml 의 Clip/Header/Weather(TimeOfDay·Rain·Snow·Fog) · Location · Distraction
    data/학습데이터/손라벨/clip_state.json 의 표시(hand=완료 · prop=전파)

사용
    python scripts/cond_inventory.py
"""
import collections
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

V = Path(__file__).resolve().parents[1]
RAW = V / "data/원본데이터"


def read_xml(p):
    try:
        h = ET.parse(p).getroot().find(".//Clip/Header")
        w = h.find("Weather")
        cond = []
        tod = w.findtext("TimeOfDay") or "?"
        cond.append(tod)
        for k, kr in (("Rain", "비"), ("Snow", "눈"), ("Fog", "안개")):
            if (w.findtext(k) or "No") not in ("No", "None"):
                cond.append(kr)
        if (h.findtext("Distraction") or "No") not in ("No", "None"):
            cond.append("방해물")
        return dict(tod=tod, cond="+".join(cond), loc=h.findtext("Location") or "?",
                    scen=ET.parse(p).getroot().findtext(".//Scenario") or "?")
    except Exception:
        return None


def main():
    marks = {}
    cs = V / "data/학습데이터/손라벨/clip_state.json"
    if cs.is_file():
        for k, v in json.load(open(cs, encoding="utf-8")).items():
            m = v.get("mark") if isinstance(v, dict) else None
            if m:
                marks[Path(k).stem] = m
    sets = sorted(p for p in RAW.glob("kisa_*") if p.is_dir())
    for s in sets:
        xmls = sorted(s.rglob("*.xml"))
        if not xmls:
            print("\n== %s : xml 없음 (%d mp4)" % (s.name, len(list(s.rglob("*.mp4"))))); continue
        by_scen = collections.defaultdict(list)
        for x in xmls:
            r = read_xml(x)
            if r:
                r["stem"] = x.stem; by_scen[r["scen"]].append(r)
        print("\n== %s : 편 %d" % (s.name, len(xmls)))
        for scen, rs in sorted(by_scen.items()):
            c = collections.Counter(r["cond"] for r in rs)
            lab = collections.Counter((r["cond"], marks.get(r["stem"], "없음")) for r in rs)
            print("  [%s] %d편" % (scen, len(rs)))
            for cond, n in c.most_common():
                hand = lab.get((cond, "hand"), 0); prop = lab.get((cond, "prop"), 0)
                tag = ("  라벨: 완료 %d · 전파 %d · 없음 %d" % (hand, prop, n - hand - prop)) if marks else ""
                print("      %-22s %3d편%s" % (cond, n, tag))
            locs = collections.Counter(r["loc"] for r in rs)
            print("      장소 %d곳: %s" % (len(locs), ", ".join("%s %d" % (k, v) for k, v in locs.most_common(8))))


if __name__ == "__main__":
    main()
