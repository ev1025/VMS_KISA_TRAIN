# -*- coding: utf-8 -*-
"""손라벨(person) 행 중 DINO 자동라벨 박스와 사실상 동일(IoU>=0.97)한 행이 얼마나 되는지 센다. 인자 --purge 면 그 행을 지운다(백업 후)."""
import json, io, glob, os, sys, collections, shutil, time
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
P = f"{V}/data/학습데이터/손라벨/person_labels.json"
rows = json.load(io.open(P, encoding="utf-8"))
dino = {}
for f in glob.glob(f"{V}/data/학습데이터/자동라벨/dino/*.json"):
    d = json.load(io.open(f, encoding="utf-8"))
    dino[os.path.basename(f)[:-5]] = d.get("frames", d) if isinstance(d, dict) else {}

def iou(a, b):
    x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[0] + a[2], b[0] + b[2]); y2 = min(a[1] + a[3], b[1] + b[3])
    i = max(0, x2 - x1) * max(0, y2 - y1)
    return i / (a[2] * a[3] + b[2] * b[3] - i + 1e-9)

same, tot, drop = collections.Counter(), collections.Counter(), []
ident = {}                                   # 행 → DINO 와 동일 여부
for r in rows:
    tot[r["clip"]] += 1
    fr = dino.get(r["clip"], {}); k = f"{float(r['t']):.1f}"; cands = fr.get(k) or []
    bx = [r["x"], r["y"], r["w"], r["h"]]
    ident[id(r)] = any(iou(bx, (c[1:5] if len(c) >= 5 else c)) >= 0.97 for c in cands)
# 규칙: 같은 프레임에 사람이 만든(DINO 와 다른) 박스가 하나라도 있고, 나머지가 DINO 와 동일하면 그 동일 박스들은 탭 때 새어 들어온 프리필로 본다.
#       프레임의 박스가 전부 DINO 와 동일하면 DINO 모드에서 사용자가 승격한 것일 수 있어 남긴다.
byf = collections.defaultdict(list)
for r in rows:
    byf[(r["clip"], f"{float(r['t']):.1f}")].append(r)
for (clip, k), rs in byf.items():
    if any(not ident[id(r)] for r in rs) and any(ident[id(r)] for r in rs):
        for r in rs:
            if ident[id(r)]:
                same[clip] += 1; drop.append(r)
allsame = sum(1 for r in rows if ident[id(r)])
print("총 손라벨 행", len(rows), "/ DINO 동일 행", allsame, "/ 그중 탭 누출로 판단(프레임에 사람 박스 공존)", len(drop))
for c in sorted(tot, key=lambda c: -tot[c])[:15]:
    print(f"  {c}: 손라벨 {tot[c]} 중 DINO동일 {same[c]}")
if "--purge" in sys.argv and drop:
    bk = f"{V}/data/학습데이터/손라벨/_backup/person_labels.{time.strftime('%Y%m%d_%H%M%S')}.json"
    shutil.copy(P, bk)
    ids = set(id(r) for r in drop)
    keep = [r for r in rows if id(r) not in ids]
    tmp = P + ".tmp_purge"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(keep, ensure_ascii=False, indent=1)); os.replace(tmp, P)
    print("삭제", len(drop), "남음", len(keep), "백업", bk)
