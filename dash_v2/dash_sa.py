# -*- coding: utf-8 -*-
"""검수 화면에 보여 줄 예측 알람(SA)을 제출 도구의 규칙으로 계산한다.

계기 (2026-09-16)
    화면(dash_v2/js/core.js)이 네 항목의 판정을 자기 나름대로 다시 구현해 두고 있었고
    상수가 전부 낡아 있었다.

        방화   화면 불 0.12 · 20창 12회 · 연기 사용   |  제출 불 0.40 · 20창 3회 · 연기 미사용
        쓰러짐 화면 th 0.269                          |  제출 th 0.755 (90.00 -> 100.00 로 바꾼 값)
        배회   화면 dwell/settle 까지만               |  제출 + 늦은 일행(20초/3명/방금 도착)
        침입   화면 gap 없음                          |  제출 gap 2

    그래서 화면의 정검/오검/미검이 서버 실측과 달랐다. 판정은 한 곳에서만 해야 한다.
    (docs/EXPERIMENTS.md "복사하지 말고 import")

여기서 하는 일
    dash_meta 를 만들 때 각 행의 sa 를 _kisa_port/tools/kisa_items.py 의 규칙으로 미리 계산해 싣는다.
    화면은 row.sa 가 있으면 그것을 쓴다(계산하지 않는다).
"""
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402


def fire_sa(signal):
    """[[t, 불, 연기]] -> SA. FireJudge 의 창 규칙과 같은 계산."""
    if not signal:
        return None
    c = K.ITEMS["fire"]
    q = deque(maxlen=c["win"])
    for t, f, s in signal:
        hit = f >= c["fire"] or (f >= 0.3 and s >= c["smoke"])
        q.append((t, hit))
        if sum(1 for _, x in q if x) >= c["hits"]:
            return round(next(t0 for t0, x in q if x) + c["delay"], 2)
    return None


def person_sa(item, tracks, poly):
    """침입·배회. 판정기는 make_judge 로 만든다(인자를 빠뜨릴 수 없게)."""
    if not tracks:
        return None
    key = "intrusion" if item == "침입" else "loitering"
    cfg = K.ITEMS[key]
    j = K.make_judge(key, cfg, "", None, None, None)
    j.poly = poly or None          # 영역은 이미 읽어 둔 것을 쓴다
    for r in tracks:
        j.feed(r["t"], r["boxes"])
    o = j.final()
    if o is None:
        return None
    return round(o + (cfg["delay"] if key == "loitering" else 0.0), 2)


def fall_sa(curves):
    """쓰러짐. 트랙별 확률 곡선에서 연속 need 창 돌파. 가장 이른 트랙."""
    if not curves:
        return None
    c = K.ITEMS["falldown"]
    th, need = c["th"], c["need"]
    best = None
    for cur in curves:
        run = 0
        for i, (t, p) in enumerate(cur):
            run = run + 1 if p >= th else 0
            if run >= need:
                t0 = cur[i - need + 1][0]
                best = t0 if best is None else min(best, t0)
                break
    return None if best is None else round(best + c.get("delay", 0.0), 2)


def attach(item, rows):
    """행 목록에 sa 를 채워 넣는다. 화면은 이 값을 그대로 쓴다."""
    for r in rows:
        try:
            if item == "방화":
                r["sa"] = fire_sa(r.get("signal"))
            elif item in ("침입", "배회"):
                r["sa"] = person_sa(item, r.get("tracks"), r.get("zone"))
            elif item == "쓰러짐":
                r["sa"] = fall_sa(r.get("curves"))
        except Exception as e:
            r["sa"] = None
            r["sa_err"] = repr(e)[:120]
    return rows
