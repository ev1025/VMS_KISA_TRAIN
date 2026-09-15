# -*- coding: utf-8 -*-
"""일회성 정리: 손라벨 박스(cls>=0)가 있는 프레임은 SAM 저장소에서 뺀다(빈 라벨 프레임은 SAM 유지)."""
import json, io, glob, os, collections, shutil, time
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
hand = collections.defaultdict(set)
for fn in ("person_labels.json", "fire_labels.json"):
    fp = f"{V}/data/학습데이터/손라벨/{fn}"
    if not os.path.exists(fp):
        continue
    for r in json.load(io.open(fp, encoding="utf-8")):
        if int(r.get("cls", -1)) >= 0:
            hand[os.path.splitext(os.path.basename(r["clip"]))[0]].add(f"{round(float(r['t']) * 2) / 2:.1f}")
tot = 0
for f in sorted(glob.glob(f"{V}/data/학습데이터/자동라벨/sam2/*.json")):
    stem = os.path.basename(f)[:-5]
    d = json.load(io.open(f, encoding="utf-8")); fr = d.get("frames") or {}
    drop = [k for k in fr if k in hand.get(stem, set())]
    if not drop:
        continue
    shutil.copy(f, f + ".bak_" + time.strftime("%H%M%S"))
    for k in drop:
        fr.pop(k)
    tmp = f + ".tmp"; io.open(tmp, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False)); os.replace(tmp, f)
    tot += len(drop)
    print(f"{stem}: SAM 프레임 {len(drop)}개 제거(손라벨 박스 있음) → 남은 SAM {sum(1 for v in fr.values() if v)}  제거={sorted(drop)}")
print("총 제거", tot)
