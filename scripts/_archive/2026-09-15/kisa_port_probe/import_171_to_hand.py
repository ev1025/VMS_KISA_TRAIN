# -*- coding: utf-8 -*-
"""AI허브 171 정답 점(객체별 키프레임 1점) → SAM 탭으로 박스를 만들어 학습 라벨(손라벨 person_labels.json)에 넣는다.
원본 XML 은 건드리지 않는다. 이미 그 클립·프레임에 손라벨이 있으면 건너뛴다. 넣은 행은 src 에 'gt:aihub171' 표시.
사용: python import_171_to_hand.py [--dry]"""
import json, io, sys, glob, os, time, shutil
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
sys.path.insert(0, V + "/dash_v2")
import serve_kisa as S
P = f"{V}/data/학습데이터/손라벨/person_labels.json"
dry = "--dry" in sys.argv
rows = json.load(io.open(P, encoding="utf-8"))
have = {(r["clip"], round(float(r["t"]), 2)) for r in rows}
added = skipped = failed = 0
for gt in sorted(glob.glob(f"{V}/data/학습데이터/정답라벨/*.json")):
    d = json.load(io.open(gt, encoding="utf-8"))
    if d.get("src") != "aihub171":
        continue
    stem = d["clip"]
    mp4 = None
    for c in glob.glob(f"{V}/data/원본데이터/aihub171_이상행동/**/{stem}.mp4", recursive=True):
        mp4 = c; break
    if not mp4:
        print("영상 없음", stem); continue
    rel = os.path.relpath(mp4, V).replace("\\", "/")
    clip = rel.replace("data/원본데이터/", "").replace(".mp4", "")
    for k, objs in (d.get("points") or {}).items():
        t = float(k)
        if (stem, round(t, 2)) in have:
            skipped += len(objs); continue
        boxes = []
        for oid, (px, py) in objs.items():
            bx, poly, score = S.sam2_mask_pts(clip, t, [[px, py, 1]])
            if bx is None:
                failed += 1; print(f"  {stem} t={t} obj{oid}: 마스크 실패(score {score:.2f})"); continue
            boxes.append((oid, bx, score))
        for oid, bx, score in boxes:
            rows.append({"file": f"{stem}_{t}.png", "clip": stem, "src": f"gt:aihub171|{rel}", "t": int(t) if t == int(t) else t, "cls": 0,
                         "x": round(bx[0], 5), "y": round(bx[1], 5), "w": round(bx[2], 5), "h": round(bx[3], 5),
                         "W": int(d.get("W") or 1920), "H": int(d.get("H") or 1080), "crop": [0, 0, int(d.get("W") or 1920), int(d.get("H") or 1080)]})
            added += 1
        print(f"{stem} t={t}: 점 {len(objs)} → 박스 {len(boxes)}")
print(f"추가 {added} · 건너뜀(이미 손라벨) {skipped} · 실패 {failed}")
if not dry and added:
    bk = f"{V}/data/학습데이터/손라벨/_backup/person_labels.{time.strftime('%Y%m%d_%H%M%S')}.before_gt171.json"
    shutil.copy(P, bk)
    tmp = P + ".tmp_gt"; io.open(tmp, "w", encoding="utf-8").write(json.dumps(rows, ensure_ascii=False, indent=1)); os.replace(tmp, P)
    print("저장", P, "백업", bk)
