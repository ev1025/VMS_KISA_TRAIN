# -*- coding: utf-8 -*-
"""손라벨 저장소에서 완전히 같은 행(클립·시각·클래스·좌표 동일)을 하나만 남긴다. 백업 후 실행."""
import json, io, os, shutil, time, collections
P = "/NHNHOME/WORKSPACE/26mss002_E3/vms/data/학습데이터/손라벨/person_labels.json"
rows = json.load(io.open(P, encoding="utf-8"))
seen = set(); keep = []; dup = 0
for r in rows:
    k = (r["clip"], round(float(r["t"]), 2), r["cls"], round(r["x"], 4), round(r["y"], 4), round(r["w"], 4), round(r["h"], 4))
    if k in seen:
        dup += 1; continue
    seen.add(k); keep.append(r)
print("완전 중복 행", dup, "→ 남음", len(keep))
if dup:
    bk = os.path.join(os.path.dirname(P), "_backup", "person_labels." + time.strftime("%Y%m%d_%H%M%S") + ".dedup.json")
    shutil.copy(P, bk)
    tmp = P + ".tmp_dedup"
    io.open(tmp, "w", encoding="utf-8").write(json.dumps(keep, ensure_ascii=False, indent=1)); os.replace(tmp, P)
    print("백업", bk)
c = collections.Counter((r["clip"], round(float(r["t"]), 2)) for r in keep if r["clip"] == "E02_001")
print("E02_001 프레임별 행:", sorted(c.items()))
