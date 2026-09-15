# -*- coding: utf-8 -*-
"""AI허브 171 이상행동 CCTV 정답(XML) → 정답라벨 저장소 data/학습데이터/정답라벨/<stem>.json
XML 은 객체별 키프레임 1개 + 그 프레임의 점(x,y) 한 개(박스 아님) + 행동 구간. 점은 SAM 탭 자리로 쓴다.
저장 형식 = SAM 저장소와 같은 틀 + points: {"frames": {}, "points": {"12.0": {"1": [x, y]}}, "events": [...], "src": "aihub171"}"""
import json, io, sys, glob, os, re
import xml.etree.ElementTree as ET
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms"
OUT = f"{V}/data/학습데이터/정답라벨"
os.makedirs(OUT, exist_ok=True)

def hms(s):
    h, m, sec = s.strip().split(":"); return int(h) * 3600 + int(m) * 60 + float(sec)

n_clip = n_pt = 0
for x in sorted(glob.glob(f"{V}/data/원본데이터/aihub171_이상행동/**/*.xml", recursive=True)):
    if "/probe_" in x:
        continue
    r = ET.parse(x).getroot()
    fn = r.findtext("filename") or os.path.basename(x).replace(".xml", ".mp4")
    stem = os.path.splitext(os.path.basename(fn))[0]
    W = int(r.findtext("size/width") or 0); H = int(r.findtext("size/height") or 0)
    fps = float(r.findtext("header/fps") or 30)
    events = []
    for ev in r.findall("event"):
        try:
            events.append({"name": ev.findtext("eventname"), "start": hms(ev.findtext("starttime")), "dur": hms(ev.findtext("duration"))})
        except Exception:
            pass
    points = {}; actions = {}
    for oi, ob in enumerate(r.findall("object"), 1):
        name = ob.findtext("objectname") or f"person_{oi}"
        m = re.search(r"(\d+)$", name); oid = int(m.group(1)) if m else oi
        for pos in ob.findall("position"):
            kf = pos.findtext("keyframe"); kx = pos.findtext("keypoint/x"); ky = pos.findtext("keypoint/y")
            if not (kf and kx and ky and W and H):
                continue
            t = round(int(kf) / fps * 2) / 2                      # 0.5초 격자
            points.setdefault(f"{t:.1f}", {})[str(oid)] = [round(float(kx) / W, 5), round(float(ky) / H, 5)]
            n_pt += 1
        acts = []
        for a in ob.findall("action"):
            for fr in a.findall("frame"):
                try:
                    acts.append({"name": a.findtext("actionname"), "start": int(fr.findtext("start")) / fps, "end": int(fr.findtext("end")) / fps})
                except Exception:
                    pass
        actions[str(oid)] = acts
    d = {"clip": stem, "src": "aihub171", "W": W, "H": H, "fps": fps, "frames": {}, "points": points, "actions": actions, "events": events,
         "note": "AI허브 171: 박스 없음. 객체별 키프레임 점(x,y) 하나 → SAM 탭 자리로 사용"}
    io.open(f"{OUT}/{stem}.json", "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
    n_clip += 1
print(f"정답라벨 저장: {n_clip}클립, 점 {n_pt}개 → {OUT}")
