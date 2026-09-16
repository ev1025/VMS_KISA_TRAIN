# -*- coding: utf-8 -*-
"""연기를 '절대 문턱' 이 아니라 '그 영상 자신의 기준선 대비 상승' 으로 보면 쓸 만해지나.

기준선 = 앞 60초 연기 신뢰도의 80퍼센타일 (kisa_items.FireJudge._baseline 과 같은 정의).
안개편은 기준선 자체가 높으므로 '상승분' 으로 보면 안 터져야 한다. 그게 통하는지 본다.
"""
import json
import sys
from collections import deque
from pathlib import Path

V = Path("/NHNHOME/WORKSPACE/26mss002_E3/vms")
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

C = K.ITEMS["fire"]
D = json.load(open(V / "dumps/score_tl/_deploy.json", encoding="utf-8"))


def baseline(rows):
    head = sorted(s for t, f, s in rows if t <= 60.0)
    return head[min(int(len(head) * 0.8), len(head) - 1)] if head else 0.0


def run(fire_th, sdelta, smin, win, hits):
    """불 >= fire_th  또는  연기 >= 기준선+sdelta 이고 연기 >= smin."""
    pairs, sas = [], {}
    for stem, e in D.items():
        base = baseline(e["rows"])
        q = deque(maxlen=win); sa = None
        for t, f, s in e["rows"]:
            hit = (fire_th is not None and f >= fire_th) or (s >= base + sdelta and s >= smin)
            q.append((t, hit))
            if sum(1 for _, x in q if x) >= hits:
                sa = next(t0 for t0, x in q if x) + C["delay"]; break
        sas[stem] = sa
        pairs.append(([{"start_s": e["gt"], "desc": "F"}],
                      [{"start_s": sa, "desc": "F"}] if sa is not None else []))
    return K.score(pairs), sas


print("기준선(앞 60초 80퍼센타일)")
for stem in sorted(D):
    print(f"  {stem}  기준선 {baseline(D[stem]['rows']):.3f}  GT {D[stem]['gt']}")

print()
print("A. 연기만, 기준선 대비 상승으로 판정  (창 20 · 3회)")
print(f"{'상승분':>8}{'최소연기':>9}{'점수':>8}{'정검':>6}{'미검':>6}{'오검':>6}")
for sd in (0.1, 0.2, 0.3, 0.4, 0.5):
    for smin in (0.3, 0.5):
        r, _ = run(None, sd, smin, C["win"], C["hits"])
        print(f"{sd:>8.2f}{smin:>9.2f}{r['점수']:>8.2f}{r['정상검출']:>6}{r['미검출']:>6}{r['오검출']:>6}")

print()
print("B. 지금 규칙(불 0.40)에 기준선 연기를 '더하면' 나아지나")
r0, s0 = run(C["fire"], 9.9, 9.9, C["win"], C["hits"])     # 연기 조건 영구 거짓 = 지금
print(f"  지금(연기 안 씀)           {r0['점수']:>7.2f}  정검 {r0['정상검출']} 미검 {r0['미검출']} 오검 {r0['오검출']}")
for sd in (0.2, 0.3, 0.4, 0.5):
    r, s = run(C["fire"], sd, 0.5, C["win"], C["hits"])
    moved = [k for k in s if s[k] != s0[k]]
    print(f"  + 연기 기준선+{sd:.1f}        {r['점수']:>7.2f}  정검 {r['정상검출']} 미검 {r['미검출']} 오검 {r['오검출']}"
          f"   바뀐 편 {len(moved)} {moved[:3]}")
