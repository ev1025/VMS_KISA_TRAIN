# -*- coding: utf-8 -*-
"""KISA 4항목 통합 SA XML 산출기 (인증 제출물).

확정 구성(2026-09-05, 전부 배포용 LOOCV 로 결정):
  fire      base 모델 + fire 채널만 conf 0.40 + 타일(전체+4분할+중앙) + 4/6창
  intrusion person_v3 + 몸전체(4꼭짓점∈구역) conf 0.40 + 2/4창
  loiter    person_v2 + 발끝∈구역 conf 0.25 + dwell 14초 연속 + onset=충족시각
  fall      yolo11x-pose + (몸통각<45° or 종횡비>=1.0) conf 0.30 + 유지 3/4 (1초 간격)

사용: python sa_runner.py --item fire|intrusion|loiter|fall --videos <폴더> --out <폴더>
      [--maps <구역맵 폴더>] [--models-dir <가중치 폴더>]
출력: 영상별 <이름>.xml (KisaLibraryIndex / Alarm / StartTime 형식, 이벤트 1건)
"""
import argparse
import math
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import cv2
from ultralytics import YOLO

DESC = {"fire": "FireDetection", "intrusion": "Intrusion",
        "loiter": "Loitering", "fall": "Falldown"}
MODEL_FILE = {"fire": "fire_base.pt", "intrusion": "person_v3.pt",
              "loiter": "person_v2.pt", "fall": "yolo11x-pose.pt"}
ZONE_TAG = {"intrusion": "Intrusion", "loiter": "Loitering"}
FIRE_DELAY_S = 10.0        # 방화 SA = onset + 10초 (점화+10초 규정)


def hms(sec):
    sec = int(round(sec))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def sa_xml(video_name, events):
    root = ET.Element("KisaLibraryIndex")
    clip = ET.SubElement(ET.SubElement(root, "Library"), "Clip")
    head = ET.SubElement(clip, "Header")
    ET.SubElement(head, "AlarmEvents").text = str(len(events))
    ET.SubElement(head, "Filename").text = video_name
    alarms = ET.SubElement(clip, "Alarms")
    for e in sorted(events, key=lambda x: x["start_s"]):
        al = ET.SubElement(alarms, "Alarm")
        ET.SubElement(al, "StartTime").text = hms(e["start_s"])
        ET.SubElement(al, "AlarmDescription").text = e["desc"]
        ET.SubElement(al, "AlarmDuration").text = hms(e.get("duration_s", 10))
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode").replace("<Alarms />", "<Alarms></Alarms>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml


def in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def zone_of(maps_dir, stem, tag):
    loc = "_".join(stem.split("_")[:2])
    r = ET.parse(Path(maps_dir) / (loc + ".map")).getroot().find(tag)
    return [tuple(map(int, p.text.split(","))) for p in r.findall("Point")]


def iter_frames(mp4, stride_s):
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, round(fps * stride_s))
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                yield i / fps, fr
        i += 1
    cap.release()


# ---------------- 항목별 onset 엔진 (확정 규칙 그대로) ----------------

def onset_fire(model, mp4):
    win = deque(maxlen=6)
    for t, fr in iter_frames(mp4, 0.5):
        h, w = fr.shape[:2]
        crops = [fr] + [fr[y:y + h // 2, x:x + w // 2] for x, y in
                        ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
        hit = False
        for c in crops:
            r = model.predict(c, conf=0.40, imgsz=640, verbose=False)[0]
            if any(r.names[int(b.cls)] == "fire" for b in r.boxes):
                hit = True
                break
        win.append((t, hit))
        if sum(1 for _, x in win if x) >= 4:
            return next(t0 for t0, x in win if x) + FIRE_DELAY_S
    return None


def onset_intrusion(model, mp4, poly):
    win = deque(maxlen=4)
    for t, fr in iter_frames(mp4, 1.0):
        hit = False
        for b in model.predict(fr, conf=0.40, imgsz=640, classes=[0], verbose=False)[0].boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            if all(in_poly(px, py, poly) for px, py in
                   ((x1, y1), (x2, y1), (x1, y2), (x2, y2))):
                hit = True
                break
        win.append((t, hit))
        if sum(1 for _, x in win if x) >= 2:
            return next(t0 for t0, x in win if x)
    return None


def onset_loiter(model, mp4, poly):
    win = deque(maxlen=14)
    for t, fr in iter_frames(mp4, 1.0):
        hit = False
        for b in model.predict(fr, conf=0.25, imgsz=640, classes=[0], verbose=False)[0].boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            if in_poly((x1 + x2) / 2, y2, poly):
                hit = True
                break
        win.append(hit)
        if len(win) == 14 and all(win):
            return t                      # onset = 체류조건 충족 시각
    return None


def onset_fall(model, mp4):
    win = deque(maxlen=4)
    for t, fr in iter_frames(mp4, 1.0):
        fallen = False
        r = model.predict(fr, conf=0.30, imgsz=640, verbose=False)[0]
        if r.keypoints is not None and len(r.boxes):
            kdata = r.keypoints.data.cpu().numpy()
            for b, kp in zip(r.boxes, kdata):
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                wide = (x2 - x1) >= (y2 - y1)
                sh = [(kp[i][0], kp[i][1]) for i in (5, 6) if kp[i][2] >= 0.2]
                hip = [(kp[i][0], kp[i][1]) for i in (11, 12) if kp[i][2] >= 0.2]
                lying = False
                if sh and hip:
                    sx = sum(p[0] for p in sh) / len(sh)
                    sy = sum(p[1] for p in sh) / len(sh)
                    hx = sum(p[0] for p in hip) / len(hip)
                    hy = sum(p[1] for p in hip) / len(hip)
                    ang = abs(math.degrees(math.atan2(hy - sy, hx - sx)))
                    lying = min(ang, 180 - ang) < 45
                if lying or wide:
                    fallen = True
                    break
        win.append((t, fallen))
        if sum(1 for _, x in win if x) >= 3:
            return next(t0 for t0, x in win if x)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--item", required=True, choices=list(DESC))
    ap.add_argument("--videos", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--maps", default="")
    ap.add_argument("--models-dir", default=".", help="fire_base.pt / person_v2.pt / person_v3.pt 위치")
    a = ap.parse_args()

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    mf = MODEL_FILE[a.item]
    model = YOLO(mf if mf.startswith("yolo") else str(Path(a.models_dir) / mf))

    for mp4 in sorted(Path(a.videos).glob("*.mp4")):
        stem = mp4.stem
        if a.item == "fire":
            o = onset_fire(model, mp4)
        elif a.item == "fall":
            o = onset_fall(model, mp4)
        else:
            poly = zone_of(a.maps, stem, ZONE_TAG[a.item])
            o = (onset_intrusion if a.item == "intrusion" else onset_loiter)(model, mp4, poly)
        events = [{"start_s": o, "desc": DESC[a.item]}] if o is not None else []
        (out / (stem + ".xml")).write_text(sa_xml(mp4.name, events), encoding="utf-8")
        print(f"{stem}: {'SA ' + hms(o) if o is not None else 'SA 없음'}", flush=True)
    print(f"완료 → {out}")


if __name__ == "__main__":
    main()
