# -*- coding: utf-8 -*-
"""검수 확대창에서 고친 프레임이 손라벨로 승격되고 SAM 저장소에서 빠졌는지 확인. 최근 수정된 SAM 저장소 클립 위주."""
import json, io, glob, os, collections, time, sys
clips = sys.argv[1:] or None
rows = json.load(io.open("data/학습데이터/손라벨/person_labels.json", encoding="utf-8"))
by = collections.defaultdict(lambda: collections.defaultdict(list))
for r in rows:
    by[r["clip"]][round(float(r["t"]) * 2) / 2].append(r)
files = sorted(glob.glob("data/학습데이터/자동라벨/sam2/*.json"), key=os.path.getmtime, reverse=True)
for f in files:
    stem = os.path.basename(f)[:-5]
    if clips and stem not in clips: continue
    d = json.load(io.open(f, encoding="utf-8")); fr = {float(k): v for k, v in d["frames"].items() if v}
    hand = by.get(stem, {})
    both = sorted(t for t in hand if t in fr)
    handbox = {t: [r for r in v if r["cls"] >= 0] for t, v in hand.items()}
    empties = sorted(t for t, v in handbox.items() if not v)
    print(f"\n== {stem}  (SAM 저장소 수정 {time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(f)))}, updated 필드 {d.get('updated')})")
    print(f"  손라벨 {len(hand)}프레임 / 박스 있는 프레임 {len([t for t in handbox if handbox[t]])} / 빈 라벨 {len(empties)}")
    print(f"  SAM 저장소 {len(fr)}프레임, 씨앗 {len(d.get('seeds', []))}")
    print(f"  손라벨·SAM 둘 다 있는 프레임(승격 뒤엔 0이어야 정상): {len(both)} {both[:10]}")
    hs = sorted(handbox)
    if hs:
        # 손라벨 프레임 중 SAM 결과 구간 안에 있는 것 = 검수에서 승격된 후보
        lo, hi = (min(fr), max(fr)) if fr else (None, None)
        inside = [t for t in hs if lo is not None and lo <= t <= hi]
        print(f"  SAM 구간({lo}~{hi}) 안의 손라벨 프레임 {len(inside)}: {inside[:20]}")
        for t in inside[:6]:
            print(f"    t={t}: 손라벨 박스 {[(round(r['x'],3), round(r['y'],3), round(r['w'],3), round(r['h'],3)) for r in handbox[t]]}  SAM에 남음: {t in fr}")
    if empties: print(f"  빈 라벨(검토완료) 프레임: {empties[:10]}")
