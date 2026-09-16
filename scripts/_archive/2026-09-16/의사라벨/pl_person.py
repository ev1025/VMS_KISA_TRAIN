# -*- coding: utf-8 -*-
"""연구개발 person 825편 → 강한 교사(yolo11x+타일)로 person 의사라벨 생성.

fire_v2 실패 교훈: 자기 자신을 교사로 쓰면 순환. 여기선 학생(yolo11s)보다
확실히 강한 교사(x+타일)를 써서 실제 새 정보(원거리·CCTV 각도 person)를 증류한다.
- 영상당 10초 간격 샘플, 상한 40장
- 병합 후 conf≥0.35 박스만 라벨로. conf 0.15 에도 아무것도 없으면 확실한 배경(빈 라벨)
- 0.15~0.35 만 있는 애매한 프레임은 버림 (오라벨 학습 방지)
- 파일명 해시로 5% 를 val 로 분리 (비디오 단위 아님 주의: 진짜 검증은 침입30 채점)
"""
import argparse
import hashlib
from pathlib import Path

import cv2
from ultralytics import YOLO


def infer_tiled(model, frame, conf):
    h, w = frame.shape[:2]
    regions = [(0, 0, w, h)] + [(x, y, w // 2, h // 2) for x, y in
               ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
    out = []
    for ox, oy, rw, rh in regions:
        r = model.predict(frame[oy:oy + rh, ox:ox + rw], conf=conf, imgsz=640,
                          classes=[0], verbose=False)[0]
        for b in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            out.append((float(b.conf), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
    return out


def nms(dets, iou_th=0.55):
    boxes = sorted(dets, key=lambda d: -d[0])
    kept = []
    while boxes:
        best = boxes.pop(0)
        kept.append(best)
        rem = []
        for d in boxes:
            xa, ya = max(best[1], d[1]), max(best[2], d[2])
            xb, yb = min(best[3], d[3]), min(best[4], d[4])
            inter = max(0, xb - xa) * max(0, yb - ya)
            a1 = (best[3] - best[1]) * (best[4] - best[2])
            a2 = (d[3] - d[1]) * (d[4] - d[2])
            if inter / (a1 + a2 - inter + 1e-6) < iou_th:
                rem.append(d)
        boxes = rem
    return kept


def split_of(stem):
    return "val" if int(hashlib.md5(stem.encode()).hexdigest(), 16) % 20 == 0 else "train"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, help="rnd_person 루트 (하위 재귀)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--teacher", default="yolo11x.pt")
    ap.add_argument("--sample-s", type=float, default=10.0)
    ap.add_argument("--cap", type=int, default=40)
    ap.add_argument("--keep-conf", type=float, default=0.35)
    ap.add_argument("--empty-conf", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=0, help="테스트용: 영상 N편만")
    a = ap.parse_args()

    out = Path(a.out)
    for sub in ("images/train", "labels/train", "images/val", "labels/val"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    model = YOLO(a.teacher)
    vids = sorted(Path(a.videos).rglob("*.mp4"))
    if a.limit:
        vids = vids[:a.limit]
    total_pos = total_neg = total_skip = 0
    for order, mp4 in enumerate(vids, 1):
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        pos = neg = skip = 0
        t = 5.0
        while t * fps < nframes - fps and pos + neg < a.cap:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
            ok, fr = cap.read()
            if ok:
                dets = nms(infer_tiled(model, fr, a.empty_conf))
                strong = [d for d in dets if d[0] >= a.keep_conf]
                stem = f"{mp4.stem}_t{int(t)}"
                sp = split_of(stem)
                h, w = fr.shape[:2]
                if strong:
                    lines = [f"0 {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} {(x2-x1)/w:.6f} {(y2-y1)/h:.6f}"
                             for _, x1, y1, x2, y2 in strong]
                    cv2.imwrite(str(out / "images" / sp / (stem + ".jpg")), fr,
                                [cv2.IMWRITE_JPEG_QUALITY, 90])
                    (out / "labels" / sp / (stem + ".txt")).write_text("\n".join(lines))
                    pos += 1
                elif not dets and neg < 10:      # 배경은 영상당 10장까지만
                    cv2.imwrite(str(out / "images" / sp / (stem + ".jpg")), fr,
                                [cv2.IMWRITE_JPEG_QUALITY, 90])
                    (out / "labels" / sp / (stem + ".txt")).write_text("")
                    neg += 1
                else:
                    skip += 1     # 애매(0.15~0.35만) → 버림
            t += a.sample_s
        cap.release()
        total_pos += pos
        total_neg += neg
        total_skip += skip
        if order % 25 == 0 or order == len(vids):
            print(f"[{order}/{len(vids)}] 누적: 라벨 {total_pos} · 배경 {total_neg} · 스킵 {total_skip}",
                  flush=True)
    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['person']\n")
    print(f"완료: 라벨 {total_pos} · 배경 {total_neg} · 스킵 {total_skip}")


if __name__ == "__main__":
    main()
