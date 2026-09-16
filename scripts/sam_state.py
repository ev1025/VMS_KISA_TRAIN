# -*- coding: utf-8 -*-
"""SAM2 전파 산출물이 어떤 모양이고 얼마나 있나. 학습셋에 들어갔나."""
import collections
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
SAM = V / "data/학습데이터/자동라벨/sam2"

js = sorted(SAM.rglob("*.json"))
print(f"SAM2 전파 파일 {len(js)}개")
if js:
    o = json.loads(js[0].read_text(encoding="utf-8"))
    print(f"  형식 예({js[0].name}): {type(o).__name__}")
    print(f"  {json.dumps(o, ensure_ascii=False)[:400]}")

tot = 0
per = {}
for f in js:
    try:
        o = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        continue
    if isinstance(o, list):
        n = len(o)
    elif isinstance(o, dict):
        n = sum(len(v) if isinstance(v, list) else 1 for v in o.values())
    else:
        n = 0
    per[f.stem] = n
    tot += n
print(f"  전체 박스(추정) {tot:,}개 · 클립 {len(per)}편")
print(f"  많은 클립 {sorted(per.items(), key=lambda x: -x[1])[:6]}")

print()
print("== handset_person_20260915 에 무엇이 들어갔나 (파일 이름 앞부분으로 가른다)")
img = V / "data/학습데이터/handset_person_20260915/images"
pre = collections.Counter()
for p in img.rglob("*"):
    if p.is_file():
        pre[p.stem.split("_")[0]] += 1
print(f"   {sum(pre.values())}장 · 앞자리 분포 {pre.most_common(12)}")
