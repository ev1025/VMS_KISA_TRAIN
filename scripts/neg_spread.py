# -*- coding: utf-8 -*-
"""뽑힌 하드네거티브가 클립 안에서 얼마나 퍼져 있나. 붙어 있으면 장수만 늘고 장면은 그대로다."""
import collections
import re
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
name = sys.argv[1] if len(sys.argv) > 1 else "handset_person_neg40_20260916"
d = V / "data/학습데이터" / name

# 라벨이 빈 파일 = 하드네거티브
neg = collections.defaultdict(list)
pos = collections.defaultdict(list)
for lab in (d / "labels").rglob("*.txt"):
    m = re.match(r"(.+)_(\d+)$", lab.stem)
    if not m:
        continue
    clip, fr = m.group(1), int(m.group(2))
    (neg if lab.stat().st_size == 0 else pos)[clip].append(fr / 100.0)

print(f"== {name}")
print(f"   네거티브 {sum(len(v) for v in neg.values()):,}장 · {len(neg)}편")
print(f"   양성     {sum(len(v) for v in pos.values()):,}장 · {len(pos)}편")
print()
print(f"   {'클립':<22}{'네거':>6}{'가장이른':>9}{'가장늦은':>9}{'퍼진폭':>8}{'평균간격':>9}")
rows = []
for clip, ts in neg.items():
    ts = sorted(ts)
    span = ts[-1] - ts[0]
    gap = span / max(1, len(ts) - 1)
    rows.append((len(ts), clip, ts[0], ts[-1], span, gap))
rows.sort(reverse=True)
for n, clip, lo, hi, span, gap in rows[:10]:
    print(f"   {clip:<22}{n:>6}{lo:>9.1f}{hi:>9.1f}{span:>8.1f}{gap:>9.2f}")
gaps = [r[5] for r in rows if r[0] > 1]
if gaps:
    gaps.sort()
    print()
    print(f"   평균간격 중앙값 {gaps[len(gaps)//2]:.2f}초  (NEG_STEP 0.5 에 가까우면 붙어 있는 것)")
