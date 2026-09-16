# -*- coding: utf-8 -*-
"""71751 라벨 전수 분석: 폴더별 파일수·클래스분포·클립수·해상도, 불/연기 관련 클래스 존재 여부."""
import json, os, sys, collections, re
from pathlib import Path
ROOT = Path(sys.argv[1])
FIRE_RE = re.compile(r"fire|smoke|flame|화재|연기|불꽃|불|smok", re.I)
per_folder = collections.defaultdict(lambda: dict(files=0, boxes=0, cats=collections.Counter(), clips=set(), sizes=collections.Counter(), groups=collections.Counter(), catnames=set(), keys=collections.Counter(), bad=0))
for p in ROOT.rglob("*.json"):
    top = p.relative_to(ROOT).parts[0]
    st = per_folder[top]; st["files"] += 1
    try: d = json.load(open(p, encoding="utf-8"))
    except Exception: st["bad"] += 1; continue
    for k in d: st["keys"][k] += 1
    cats = {c.get("category_index", c.get("id")): c.get("category_name", c.get("name")) for c in d.get("categories", [])}
    st["catnames"].update(v for v in cats.values() if v)
    img = d.get("image", {}); st["sizes"][(img.get("width"), img.get("height"))] += 1
    at = d.get("attributes", {}); st["clips"].add(at.get("clipname")); st["groups"][at.get("group")] += 1
    for a in d.get("annotations", []):
        st["boxes"] += 1; st["cats"][cats.get(a.get("categories_id", a.get("category_id")), "?")] += 1
for top, st in sorted(per_folder.items()):
    print(f"\n##### {top}")
    print(f"files={st['files']} bad={st['bad']} boxes={st['boxes']} clips={len(st['clips'])}")
    print("keys:", dict(st["keys"]))
    print("sizes:", st["sizes"].most_common(5))
    print("groups:", st["groups"].most_common(20))
    print("catnames(정의):", sorted(st["catnames"]))
    print("cats(실제 박스):", st["cats"].most_common(30))
    hit = [c for c in st["catnames"] if FIRE_RE.search(str(c))]
    print("불/연기 관련 클래스:", hit or "없음")
