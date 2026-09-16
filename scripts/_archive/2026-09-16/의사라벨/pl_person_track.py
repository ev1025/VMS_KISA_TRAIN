# -*- coding: utf-8 -*-
"""야간 person 영상에 트랙 검증 라벨 생성: conf 필터 대신 '트랙 길이'로 라벨 채택.

기존 pl_person 은 conf<0.35 프레임을 버려서 야간 약신호가 라벨에 못 들어갔다.
여기선 x 교사로 GT 전후 2분을 추적(ByteTrack)해서, 오래 유지된 트랙(길이>=6표본)의
박스는 conf 가 낮아도 진짜 사람으로 보고 라벨로 쓴다. 야간(어두운) 영상만 대상.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
from ultralytics import YOLO


def hms(t):
    h, m, s = (t or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def gt_start(xml_path):
    try:
        al = ET.parse(xml_path).getroot().find(".//Alarm")
        return hms(al.findtext("StartTime")) if al is not None else None
    except Exception:
        return None


def is_dark(cap, fps, t):
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
    ok, fr = cap.read()
    return ok and cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).mean() < 65


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--teacher", default="yolo11x.pt")
    ap.add_argument("--min-track", type=int, default=6)
    ap.add_argument("--save-every", type=int, default=4, help="추적 표본 N개마다 1장 라벨 저장")
    a = ap.parse_args()

    out = Path(a.out)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    model = YOLO(a.teacher)
    vids = sorted(Path(a.videos).rglob("*.mp4"))
    n_night = n_saved = 0
    for mp4 in vids:
        start = gt_start(mp4.with_suffix(".xml"))
        if start is None:
            continue
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        dark = is_dark(cap, fps, max(2, start - 30))
        if not dark:
            cap.release()
            continue
        n_night += 1
        # GT 전후 2분 구간을 3fps 로 추적
        t0, t1 = max(0, start - 60), start + 60
        step = max(1, round(fps / 3))
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t0 * fps))
        frames = []          # (프레임 인덱스, 이미지) 표본
        idx = int(t0 * fps)
        while idx < t1 * fps:
            if not cap.grab():
                break
            if (idx - int(t0 * fps)) % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    frames.append((idx, fr))
            idx += 1
        cap.release()
        if len(frames) < 10:
            continue
        # 추적 (persist 스트림)
        tracks = defaultdict(list)    # id -> [(표본번호, conf, box)]
        per_frame = defaultdict(list) # 표본번호 -> [(id, conf, box)]
        model.predict  # noqa
        for si, (_, fr) in enumerate(frames):
            r = model.track(fr, persist=True, conf=0.15, imgsz=640, classes=[0],
                            verbose=False, tracker="bytetrack.yaml")[0]
            if r.boxes.id is None:
                continue
            for b in r.boxes:
                tid = int(b.id)
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                tracks[tid].append(si)
                per_frame[si].append((tid, float(b.conf), (x1, y1, x2, y2)))
        good = {tid for tid, sis in tracks.items() if len(sis) >= a.min_track}
        if not good:
            continue
        saved = 0
        for si in sorted(per_frame):
            if si % a.save_every:
                continue
            boxes = [(c, bx) for tid, c, bx in per_frame[si] if tid in good]
            if not boxes:
                continue
            fr = frames[si][1]
            h, w = fr.shape[:2]
            stem = f"{mp4.stem}_trk{si}"
            cv2.imwrite(str(out / "images" / (stem + ".jpg")), fr, [cv2.IMWRITE_JPEG_QUALITY, 90])
            (out / "labels" / (stem + ".txt")).write_text("\n".join(
                f"0 {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}"
                for _, (x1, y1, x2, y2) in boxes))
            saved += 1
        n_saved += saved
        print(f"{mp4.stem}: 야간, 유효트랙 {len(good)}개, 라벨 {saved}장 (누적 {n_saved})", flush=True)
        # 트래커 상태 초기화 (영상 간 ID 오염 방지)
        if hasattr(model, "predictor") and model.predictor is not None:
            model.predictor.trackers = None if not hasattr(model.predictor, "trackers") else []
            model.predictor = None
    print(f"완료: 야간 {n_night}편, 라벨 {n_saved}장")


if __name__ == "__main__":
    main()
