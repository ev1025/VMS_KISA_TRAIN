# -*- coding: utf-8 -*-
"""채점셋(kisa_배포_검증영상) 라벨이 학습셋에 들어갔는지 확인한다. 들어갔으면 점수가 전부 무효다."""
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
L = V / "data/학습데이터/손라벨"
EVAL_MARK = "kisa_배포_검증영상"


def split(fn):
    rows = json.loads((L / fn).read_text(encoding="utf-8"))
    ev = [r for r in rows if EVAL_MARK in (r.get("src") or "")]
    tr = [r for r in rows if EVAL_MARK not in (r.get("src") or "")]
    return rows, ev, tr


for fn, tag in (("fire_labels.json", "방화"), ("person_labels.json", "사람")):
    rows, ev, tr = split(fn)
    evf = {(r.get("clip"), r.get("file")) for r in ev}
    trf = {(r.get("clip"), r.get("file")) for r in tr}
    print(f"== {tag} 손라벨 {len(rows):,}박스")
    print(f"   학습에 쓸 수 있는 것  {len(tr):,}박스 / {len(trf):,}장 (연구개발·아이허브 등)")
    print(f"   채점셋(쓰면 안 됨)    {len(ev):,}박스 / {len(evf):,}장")
    print(f"   채점셋 클립 {sorted({r.get('clip') for r in ev})}")
    print()

print("== 학습셋 폴더에 채점셋 프레임이 들어갔나")
for d in sorted((V / "data/학습데이터").glob("handset_*")):
    img = d / "images"
    if not img.is_dir():
        continue
    names = [p.stem for p in img.rglob("*") if p.is_file()]
    bad = [n for n in names if n.startswith("C00_")]
    mark = "  <<< 누수" if bad else "  깨끗"
    print(f"   {d.name:<32}{len(names):>6}장 · C00_ 로 시작하는 것 {len(bad):>4}개{mark}")
    if bad:
        print(f"      예: {bad[:6]}")

print()
print("== 검증셋(evalset_fire) 은 채점셋이어야 정상")
for d in ("evalset_fire", "evalset_person"):
    img = V / "data/학습데이터" / d / "images"
    if img.is_dir():
        names = [p.stem for p in img.rglob("*") if p.is_file()]
        c00 = sum(1 for n in names if n.startswith("C00_"))
        print(f"   {d:<20}{len(names):>6}장 · C00_ {c00}개 ({c00/max(1,len(names))*100:.0f}%)")
