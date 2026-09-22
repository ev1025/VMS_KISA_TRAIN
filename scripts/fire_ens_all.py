# -*- coding: utf-8 -*-
"""방화 앙상블을 전수로 훑는다. 덤프만 쓰므로 추론이 없다.

왜 (2026-09-17)
    지금 배포는 fire_fog + fire_small 2벌로 100.00 인데, 그 100 이 한 편(C00_195_0001)
    표본 3개에 매달려 있다. 실제 시험은 편이 10배라 그 편이 빗나가면 만회가 안 된다.
    mAP 상위 모델(s2_m640·g_wildpos 등)은 앙상블 후보로 써 본 적이 없다.

무엇을 보나
    점수만 보지 않는다. 같은 점수면 '아슬아슬한 편이 적은 쪽' 이 실제 시험에서 안전하다.
    아슬 = 정검이긴 한데 창 경계까지 1초 이하로 남은 편.

사용
    python scripts/fire_ens_all.py            # 단독 + 2벌 전수
    python scripts/fire_ens_all.py --top 20   # 상위 몇 개까지 볼지
"""
import argparse
import itertools
import json
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

C = K.ITEMS["fire"]
TL = V / "dumps/score_tl"
DEPLOY = ["fresh_48k_wildall_20260909", "s2_s960_20260913"]   # fire_fog.pt · fire_small.pt
SKIP = {"_deploy", "best"}                                    # 합성·별칭 덤프는 뺀다(같은 것을 두 번 세지 않게)

ap = argparse.ArgumentParser()
ap.add_argument("--top", type=int, default=15)
a = ap.parse_args()

_CACHE = {}


def load(name):
    if name not in _CACHE:
        _CACHE[name] = json.loads((TL / (name + ".json")).read_text(encoding="utf-8"))
    return _CACHE[name]


def merge(names):
    """원소별 max. 앙상블 = 표본마다 여러 모델의 최고 신뢰도."""
    parts = [load(n) for n in names]
    out = {}
    for stem, e in parts[0].items():
        rows = {round(r[0], 2): [r[1], r[2]] for r in e["rows"]}
        for o in parts[1:]:
            for r in (o.get(stem) or {}).get("rows", []):
                k = round(r[0], 2)
                if k in rows:
                    rows[k][0] = max(rows[k][0], r[1]); rows[k][1] = max(rows[k][1], r[2])
                else:
                    rows[k] = [r[1], r[2]]
        out[stem] = {"rows": [[t, v[0], v[1]] for t, v in sorted(rows.items())], "gt": e["gt"]}
    return out


def judge(rows):
    q = deque(maxlen=C["win"])
    for t, f, s in rows:
        q.append((t, f >= C["fire"] or (f >= 0.3 and s >= C["smoke"])))
        if sum(1 for _, x in q if x) >= C["hits"]:
            return next(t0 for t0, x in q if x) + C["delay"]
    return None


def evaluate(names):
    d = merge(names)
    pairs, miss, thin = [], [], []
    for stem, e in sorted(d.items()):
        gt = e["gt"]; sa = judge(e["rows"])
        pairs.append(([{"start_s": gt, "desc": "F"}],
                      [{"start_s": sa, "desc": "F"}] if sa is not None else []))
        if sa is None or not (gt - 2 <= sa <= gt + 10):
            miss.append(stem)
        else:
            m = min(round(gt + 10 - sa, 1), round(sa - (gt - 2), 1))
            if m <= 1.0:
                thin.append(stem)
    return K.score(pairs)["점수"], miss, thin


names = sorted(p.stem for p in TL.glob("*.json") if p.stem not in SKIP)
print(f"덤프 {len(names)}개 · 규칙(제출 도구): 불 {C['fire']} · 창 {C['win']} · {C['hits']}회 · 지연 {C['delay']}")
print("아슬 = 정검이지만 창 경계까지 1초 이하. 같은 점수면 이게 적은 쪽이 실제 시험에서 안전하다.\n")

rows = []
for n in names:
    try:
        rows.append((evaluate([n]), (n,)))
    except Exception:
        pass
n_single = len(rows)
for x, y in itertools.combinations(names, 2):
    try:
        rows.append((evaluate([x, y]), (x, y)))
    except Exception:
        pass
print(f"단독 {n_single}개 · 2벌 {len(rows) - n_single}개 훑음\n")

rows.sort(key=lambda r: (-r[0][0], len(r[0][2]), len(r[0][1])))   # 점수 높고 · 아슬 적고 · 미검 적은 순
print("%7s %5s %5s  %s" % ("점수", "아슬", "미검", "구성"))
for (sc, miss, thin), combo in rows[:a.top]:
    mark = "  <- 지금 배포" if sorted(combo) == sorted(DEPLOY) else ""
    print("%7.2f %5d %5d  %s%s" % (sc, len(thin), len(miss), " + ".join(combo), mark))

dep = next((r for r in rows if sorted(r[1]) == sorted(DEPLOY)), None)
if dep:
    (sc, miss, thin), _ = dep
    print(f"\n지금 배포: {sc:.2f} · 아슬 {len(thin)}편 {thin} · 미검 {len(miss)}편 {miss}")
    print(f"순위: {rows.index(dep) + 1} / {len(rows)}")
