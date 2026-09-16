# -*- coding: utf-8 -*-
"""71751 라벨 zip 을 풀지 않고 직접 읽어 분석. 1) 파일명으로 폴더 구성 즉시 출력 2) 전수 JSON 파싱으로 클래스 분포."""
import zipfile, json, sys, collections, re, time
from pathlib import Path
FIRE_RE = re.compile(r"fire|smoke|flame|화재|연기|불꽃", re.I)
def p(*a): print(*a, flush=True)
for zp in sys.argv[1:]:
    zf = zipfile.ZipFile(zp); names = [n for n in zf.namelist() if n.lower().endswith(".json")]
    p(f"\n################ {Path(zp).name}: json {len(names)}개")
    # 1) 폴더 구성 (파일명만)
    depth = collections.Counter(n.count("/") for n in names)
    p("경로 깊이 분포:", dict(depth))
    for lv in (0, 1, 2):
        c = collections.Counter("/".join(n.split("/")[:lv+1]) for n in names if n.count("/") > lv)
        if c: p(f"[깊이{lv}] 폴더 {len(c)}개:", c.most_common(25))
    # 파일명 접두(group) 분포
    pre = collections.Counter(Path(n).name.split("_")[0] for n in names)
    p("파일명 접두 분포:", pre.most_common(30))
    # 2) 전수 파싱
    st = collections.defaultdict(lambda: dict(files=0, boxes=0, cats=collections.Counter(), clips=set(), sizes=collections.Counter(), catnames=set(), keys=collections.Counter(), attrs=collections.defaultdict(collections.Counter), bad=0))
    t0 = time.time()
    for i, n in enumerate(names):
        top = n.split("/")[0] if "/" in n else "(root)"
        s = st[top]; s["files"] += 1
        try: d = json.loads(zf.read(n))
        except Exception: s["bad"] += 1; continue
        for k in d: s["keys"][k] += 1
        cats = {c.get("category_index", c.get("id")): c.get("category_name", c.get("name")) for c in d.get("categories", [])}
        s["catnames"].update(v for v in cats.values() if v)
        img = d.get("image", {}); s["sizes"][(img.get("width"), img.get("height"))] += 1
        at = d.get("attributes", {}) or {}
        s["clips"].add(at.get("clipname"))
        for k, v in at.items():
            if k not in ("scene", "clipname"): s["attrs"][k][str(v)] += 1
        for a in d.get("annotations", []) or []:
            s["boxes"] += 1; s["cats"][cats.get(a.get("categories_id", a.get("category_id")), "?")] += 1
        if i % 200000 == 0 and i: p(f"  ..{i}/{len(names)} {time.time()-t0:.0f}s")
    for top, s in sorted(st.items()):
        p(f"\n===== {top}: files={s['files']} bad={s['bad']} boxes={s['boxes']} clips={len(s['clips'])}")
        p("  keys:", dict(s["keys"]))
        p("  sizes:", s["sizes"].most_common(5))
        for k, c in s["attrs"].items(): p(f"  attr.{k}:", c.most_common(15))
        p("  catnames:", sorted(s["catnames"]))
        p("  boxes/cat:", s["cats"].most_common(30))
        hit = [c for c in s["catnames"] if FIRE_RE.search(str(c))]
        p("  ★불/연기 클래스:", hit or "없음")
