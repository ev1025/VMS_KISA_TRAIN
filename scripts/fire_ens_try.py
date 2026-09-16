# -*- coding: utf-8 -*-
"""가중치 여러 벌을 겹쳤을 때 방화 점수가 얼마인지, 덤프만으로 잰다.

왜 추론이 필요 없나
    앙상블은 '표본마다 두(또는 그 이상) 모델의 최고 신뢰도' 를 쓴다.
    그러니 각 모델의 덤프를 원소별 max 로 합치면 그게 곧 앙상블 신호다.
    새 가중치를 학습해 덤프가 생기면, 추론을 다시 안 하고 여기서 조합만 바꿔 보면 된다.

규칙은 제출 도구(_kisa_port/tools/kisa_items.py)의 ITEMS["fire"] 를 그대로 쓴다.

사용
    python scripts/fire_ens_try.py                      # 기본 조합 비교
    python scripts/fire_ens_try.py A B C                # 그 덤프들을 겹친 점수 하나
"""
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
# 배포 가중치가 어느 덤프에서 왔는지. scripts/make_deploy_signal.py 와 같은 표다.
DEPLOY = {"fire_fog.pt": "fresh_48k_wildall_20260909", "fire_small.pt": "s2_s960_20260913"}


def load(name):
    f = TL / (name + ".json")
    if not f.is_file():
        raise SystemExit(f"덤프 없음: {f}")
    return json.loads(f.read_text(encoding="utf-8"))


def merge(names):
    """원소별 max. 첫 덤프의 클립 목록을 기준으로 한다."""
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
                thin.append(f"{stem}({m}s)")
    r = K.score(pairs)
    return r, miss, thin


def show(label, names):
    try:
        r, miss, thin = evaluate(names)
    except SystemExit as e:
        print(f"  {label:<34} {e}")
        return
    print(f"  {label:<34} {r['점수']:>6.2f}  (정검 {r['정상검출']:>2} 미검 {r['미검출']} 오검 {r['오검출']})"
          f"  못잡음 {miss if miss else '-'}  아슬 {thin if thin else '-'}")


if __name__ == "__main__":
    print(f"규칙(제출 도구): 불 {C['fire']} · 창 {C['win']} · {C['hits']}회 · 지연 {C['delay']}\n")
    if len(sys.argv) > 1:
        show(" + ".join(sys.argv[1:]), sys.argv[1:])
        raise SystemExit(0)

    fog, small = DEPLOY["fire_fog.pt"], DEPLOY["fire_small.pt"]
    NEW = [n for n in ("f1280_best_s_20260915", "f960_best_s_20260915") if (TL / (n + ".json")).is_file()]
    print("=== 지금 배포와 그 부분들")
    show("fire_fog 단독", [fog])
    show("fire_small 단독", [small])
    show("fire_fog + fire_small (지금 배포)", [fog, small])
    for n in NEW:
        print(f"\n=== {n} 를 넣으면")
        show(f"{n} 단독", [n])
        show(f"fire_fog + {n}", [fog, n])
        show(f"fire_small + {n}", [small, n])
        show(f"배포 + {n} (3벌)", [fog, small, n])
    if len(NEW) == 2:
        print("\n=== 새 둘만 / 전부")
        show("새 둘만", NEW)
        show("네 벌 전부", [fog, small] + NEW)
