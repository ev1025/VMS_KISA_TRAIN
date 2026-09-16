# -*- coding: utf-8 -*-
"""손라벨·전파의 현재 상태와, 학습셋에 실제로 들어간 양을 비교한다."""
import collections
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
L = V / "data/학습데이터/손라벨"


def look(fn, label):
    p = L / fn
    if not p.is_file():
        print(f"{label}: 파일 없음"); return
    rows = json.loads(p.read_text(encoding="utf-8"))
    clips = collections.Counter(r.get("clip", "?") for r in rows)
    files = {(r.get("clip"), r.get("file")) for r in rows}
    src = collections.Counter(r.get("src", "손") or "손" for r in rows)
    cls = collections.Counter(r.get("cls") for r in rows)
    print(f"== {label}  ({p.stat().st_size/1024:.0f}KB, {p.stat().st_mtime:.0f})")
    print(f"   박스 {len(rows):,}개 · 프레임 {len(files):,}장 · 클립 {len(clips)}편")
    print(f"   클래스 {dict(cls)}")
    print(f"   출처 {dict(src)}")
    top = clips.most_common(5)
    print(f"   많은 클립 {top}")
    return rows


fire = look("fire_labels.json", "방화 손라벨")
print()
person = look("person_labels.json", "사람 손라벨")

print()
print("== 학습셋에 들어간 양 (build 시점 고정)")
for d in sorted((V / "data/학습데이터").glob("handset_*")):
    img = d / "images"
    lab = d / "labels"
    n = sum(1 for _ in img.rglob("*")) if img.is_dir() else 0
    nb = 0
    if lab.is_dir():
        for f in lab.rglob("*.txt"):
            nb += sum(1 for _ in f.open())
    import datetime
    t = datetime.datetime.fromtimestamp(d.stat().st_mtime).strftime("%m-%d %H:%M")
    print(f"   {d.name:<32}{n:>7}장 {nb:>7}박스   빌드 {t}")

print()
print("== 전파(SAM2)")
sam = V / "data/학습데이터/자동라벨/sam2"
if sam.is_dir():
    js = list(sam.rglob("*.json"))
    print(f"   {sam} · 파일 {len(js)}개")
    tot = 0
    for f in js[:200]:
        try:
            o = json.loads(f.read_text(encoding="utf-8"))
            tot += len(o) if isinstance(o, list) else len(o.get("boxes", []) or [])
        except Exception:
            pass
    print(f"   앞 200개 파일에서 박스 {tot:,}개")
    for f in sorted(js, key=lambda x: -x.stat().st_mtime)[:5]:
        import datetime
        print(f"     {datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime('%m-%d %H:%M')}  {f.relative_to(sam)}")
