# -*- coding: utf-8 -*-
"""--neg 를 올리면 하드네거티브가 실제로 늘어나는가.

빌더는 클립당 min(2*neg, 손라벨 프레임 수) 장을 뽑는다.
둘 중 어느 쪽이 실제로 걸리는지 봐야 --neg 를 올리는 게 의미가 있는지 안다.
"""
import collections
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
L = V / "data/학습데이터/손라벨"
EVAL = "kisa_배포_검증영상"

for fn, tag in (("person_labels.json", "사람"), ("fire_labels.json", "방화")):
    rows = json.loads((L / fn).read_text(encoding="utf-8"))
    # 채점셋은 네거티브로도 못 쓴다
    rows = [r for r in rows if EVAL not in (r.get("src") or "")]
    per = collections.defaultdict(set)
    for r in rows:
        per[r.get("clip")].add(r.get("file"))
    n = {k: len(v) for k, v in per.items()}
    print(f"== {tag}   손라벨 클립 {len(n)}편 · 양성 프레임 {sum(n.values())}장")
    dist = collections.Counter()
    for v in n.values():
        dist["1~2장" if v <= 2 else "3~5장" if v <= 5 else "6~10장" if v <= 10 else "11장 이상"] += 1
    for k in ("1~2장", "3~5장", "6~10장", "11장 이상"):
        print(f"   클립당 손라벨 {k:<9}{dist[k]:>4}편")
    print(f"   {'--neg':>6}{'뽑히는 네거티브':>14}{'라벨수에 걸린 클립':>18}{'neg 에 걸린 클립':>16}")
    for neg in (5, 10, 20, 40):
        cap = 2 * neg
        tot = sum(min(cap, v) for v in n.values())
        by_label = sum(1 for v in n.values() if v < cap)
        by_neg = sum(1 for v in n.values() if v >= cap)
        print(f"   {neg:>6}{tot:>14}{by_label:>18}{by_neg:>16}")
    print()
