# -*- coding: utf-8 -*-
"""디코더 차이 정량화(2026-09-20). 같은 mp4 의 같은 프레임 번호를 (1) OpenCV VideoCapture (2) PyAV 로 디코드해 .npy 로 저장한다.
서버 npy 와 비교하면 장비·디코더별 픽셀 차이(평균 절대차, 채널 편향, 공간 이동)를 잴 수 있다.
사용: python decode_probe.py --videos <폴더> --out <폴더> --clips C00_235_0002:15.0,16.0,17.0 [--stride 0.1]
"""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np


def cv2_frame(mp4, target):
    cap = cv2.VideoCapture(str(mp4)); i = 0; fr = None
    while i <= target:
        if not cap.grab():
            break
        if i == target:
            _ok, fr = cap.retrieve()
        i += 1
    fps = cap.get(cv2.CAP_PROP_FPS); cap.release()
    return fr, fps


def av_frame(mp4, target):
    try:
        import av
    except ImportError:
        return None, "PyAV 없음"
    with av.open(str(mp4)) as c:
        st = c.streams.video[0]
        for i, f in enumerate(c.decode(st)):
            if i == target:
                return f.to_ndarray(format="bgr24"), str(st.codec_context.name)
    return None, "끝까지 못 찾음"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--clips", nargs="*", default=["C00_153_0005:113.0", "C00_235_0002:15.0,16.0,17.0,18.0"])
    ap.add_argument("--stride", type=float, default=0.1)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    rep = {"cv2": cv2.__version__, "cv2_build_ffmpeg": [l.strip() for l in cv2.getBuildInformation().splitlines() if "FFMPEG" in l or "avcodec" in l][:3], "frames": {}}
    for spec in a.clips:
        stem, ts = spec.split(":")
        mp4 = next(Path(a.videos).rglob(stem + ".mp4"))
        for t in ts.split(","):
            t = float(t)
            cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)); cap.release()
            step = max(1, round(fps * a.stride)); target = round(t * fps / step) * step
            key = f"{stem}_{t:.1f}"
            fr, _ = cv2_frame(mp4, target)
            fa, codec = av_frame(mp4, target)
            r = {"fps": fps, "frame_count": n, "frame_index": target, "codec": codec}
            if fr is not None:
                np.save(out / f"{key}_cv2.npy", fr); r["cv2_md5"] = hashlib.md5(fr.tobytes()).hexdigest()
            if fa is not None:
                np.save(out / f"{key}_av.npy", fa); r["av_md5"] = hashlib.md5(fa.tobytes()).hexdigest()
                if fr is not None:
                    d = np.abs(fr.astype(np.int16) - fa.astype(np.int16)); r["cv2_vs_av_mean_abs"] = float(d.mean()); r["cv2_vs_av_max"] = int(d.max())
            rep["frames"][key] = r
            print(key, r, flush=True)
    (out / "decode_probe.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print("끝")


if __name__ == "__main__":
    main()
