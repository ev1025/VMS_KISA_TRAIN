# -*- coding: utf-8 -*-
"""PoseC3D 용 조밀 다인 원시 키포인트 추출. 기존 59차원(top-1 정규화)과 달리
   stride 0.1s, 최대 5인, 절대 픽셀 좌표 저장 → 폐색·원거리에서 저신뢰 인물도 보존.

2026-09-20 추가
   --imgsz  자세 입력 해상도(기본 640 = 기존 feats/fall_kpts 와 동일). 배포는 1280 이라 feats/fall_kpts_1280 재추출에 쓴다.
   --batch  프레임을 이만큼 모아 한 번에 추론(기본 1 = 기존과 동일). 학습과 GPU 를 나눠 쓸 때 편당 2.5분 → 배치 16 으로 줄인다.
            ultralytics 는 배치 안 이미지를 각각 letterbox 하므로 결과는 낱장 추론과 같다.
"""
import argparse, xml.etree.ElementTree as ET
from pathlib import Path
import cv2, numpy as np
from ultralytics import YOLO


def hms(t):
    h, m, s = (t or "0:0:0").split(":"); return int(h) * 3600 + int(m) * 60 + int(s)


def gt_info(xml):
    try:
        al = ET.parse(xml).getroot().find(".//Alarm")
        return (hms(al.findtext("StartTime")), hms(al.findtext("AlarmDuration")) or 10) if al is not None else (None, None)
    except Exception:
        return None, None


def to_kpts(r, maxp):
    """결과 하나 → (maxp, 17, 3) 절대픽셀 키포인트(신뢰도 상위 maxp 명)."""
    fr_k = np.zeros((maxp, 17, 3), np.float32)
    if r.keypoints is not None and len(r.boxes):
        confs = r.boxes.conf.cpu().numpy()
        idx = np.argsort(confs)[::-1][:maxp]
        kp = r.keypoints.data.cpu().numpy()
        for j, id_ in enumerate(idx):
            fr_k[j] = kp[id_]
    return fr_k


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=float, default=0.1)   # 10fps
    ap.add_argument("--maxp", type=int, default=5)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--noise", type=int, default=0, help="픽셀의 N%% 에 ±1 무작위 잡음(프레임 번호로 결정적). 디코더 반올림 무늬 흉내(2026-09-21)")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    model = YOLO("yolo11x-pose.pt")
    vids = []
    for d in a.videos:
        vids += sorted(Path(d).rglob("*.mp4"))
    for order, mp4 in enumerate(vids, 1):
        dst = out / (mp4.stem + ".npz")
        if dst.exists():
            continue
        start, dur = gt_info(mp4.with_suffix(".xml"))
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step = max(1, round(fps * a.stride)); i = 0; ts = []; kseq = []; WH = None
        buf, buf_t = [], []

        def flush():
            if not buf:
                return
            for r, t in zip(model.predict(buf, conf=0.10, imgsz=a.imgsz, verbose=False), buf_t):
                ts.append(t); kseq.append(to_kpts(r, a.maxp))
            buf.clear(); buf_t.clear()

        while True:
            if not cap.grab(): break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    if WH is None: WH = (fr.shape[1], fr.shape[0])
                    if a.noise:
                        rng = np.random.default_rng(i); mask = rng.random(fr.shape[:2]) < a.noise / 100.0
                        sign = rng.integers(0, 2, fr.shape[:2]).astype(np.int16) * 2 - 1
                        fr = np.clip(fr.astype(np.int16) + (mask * sign).astype(np.int16)[..., None], 0, 255).astype(np.uint8)
                    buf.append(fr); buf_t.append(i / fps)
                    if len(buf) >= a.batch:
                        flush()
            i += 1
        flush()
        cap.release()
        np.savez_compressed(dst, t=np.array(ts, np.float32),
                            kpts=np.stack(kseq) if kseq else np.zeros((0, a.maxp, 17, 3), np.float32),
                            wh=np.array(WH or (0, 0), np.int32),
                            gt_start=-1.0 if start is None else float(start),
                            gt_dur=0.0 if dur is None else float(dur))
        if order % 20 == 0 or order == len(vids):
            print(f"[{order}/{len(vids)}] {mp4.stem} 표본 {len(ts)}", flush=True)
    print("완료")


if __name__ == "__main__":
    main()
