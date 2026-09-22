# -*- coding: utf-8 -*-
"""장비 간 자세 추론 불일치 진단(2026-09-20). 제미나이 제안 2번 '입력 통제 실험' 을 그대로 한다.

서버·Thor 양쪽에서 같은 스크립트를 돈다.
  save 모드(서버):  지정 편·프레임을 배포 경로와 같은 방식(cv2 grab/retrieve, 3프레임마다)으로 디코드해 .npy 로 저장하고, 그 프레임에 자세 모델을 돌려 결과 json 을 남긴다.
  thor 모드(Thor): 서버가 준 .npy(같은 픽셀)에 자세 모델을 돌린 결과 + Thor 가 직접 디코드한 같은 프레임의 md5·자세 결과를 남긴다.
비교하면 디코더 차이(픽셀 md5)와 추론 차이(같은 픽셀 → 다른 키포인트)를 가를 수 있다. 결과 dtype 으로 FP16 여부도 본다.

사용
  서버: python frame_probe.py save --videos <쓰러짐 견본 폴더> --out <폴더> --clips C00_153_0005:113.0,113.5 C00_235_0002:15.0,16.0,17.0
  Thor: python frame_probe.py thor --videos /data/영상/falldown --npy <서버 npy 폴더> --out <폴더>
"""
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).resolve().parent))
import kisa_paths as _KP
import argparse
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import torch


def decode_frame(mp4, t_sec, stride=0.1):
    """배포 경로와 같은 방식: grab 로 넘기다가 step 배수 프레임만 retrieve. t_sec 에 가장 가까운 표본 프레임을 준다."""
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * stride))
    target = round(t_sec * fps / step) * step
    i = 0; fr = None
    while i <= target:
        if not cap.grab():
            break
        if i == target:
            ok, fr = cap.retrieve()
        i += 1
    cap.release()
    return fr, fps, target


def pose_json(model, img, imgsz=1280, conf=0.10):
    r = model.predict(img, conf=conf, imgsz=imgsz, verbose=False)[0]
    out = {"dtype": str(r.boxes.data.dtype) if len(r.boxes) else "none", "n": int(len(r.boxes)), "persons": []}
    if len(r.boxes):
        kp = r.keypoints.data.cpu().numpy(); bx = r.boxes.data.cpu().numpy()
        order = np.argsort(-bx[:, 4])
        for j in order:
            out["persons"].append({"conf": round(float(bx[j, 4]), 4), "box": [round(float(v), 1) for v in bx[j, :4]],
                                   "kp": [[round(float(x), 1), round(float(y), 1), round(float(c), 3)] for x, y, c in kp[j]]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["save", "thor"])
    ap.add_argument("--videos", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--npy", default=None)
    ap.add_argument("--clips", nargs="*", default=["C00_153_0005:112.0,113.0,113.5,114.0", "C00_235_0002:14.5,15.0,16.0,17.0,18.0"])
    ap.add_argument("--weights", default=str(_KP.V / "model/yolo11x-pose.pt"))
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO
    model = YOLO(a.weights)
    env = {"torch": torch.__version__, "cuda": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
           "cv2": cv2.__version__, "numpy": np.__version__,
           "tf32_cudnn": torch.backends.cudnn.allow_tf32, "tf32_matmul": torch.backends.cuda.matmul.allow_tf32}
    try:
        import ultralytics; env["ultralytics"] = ultralytics.__version__
    except Exception:
        pass
    report = {"env": env, "frames": {}}
    for spec in a.clips:
        stem, ts = spec.split(":")
        mp4 = next(Path(a.videos).rglob(stem + ".mp4"))
        for t in ts.split(","):
            t = float(t); key = f"{stem}@{t:.1f}"
            fr, fps, idx = decode_frame(mp4, t)
            if fr is None:
                report["frames"][key] = {"error": "decode 실패"}; continue
            rec = {"fps": fps, "frame_index": idx, "own_decode_md5": hashlib.md5(fr.tobytes()).hexdigest(),
                   "own_decode_pose": pose_json(model, fr)}
            if a.mode == "save":
                np.save(out / (key.replace("@", "_") + ".npy"), fr)
            else:
                f = Path(a.npy) / (key.replace("@", "_") + ".npy")
                if f.is_file():
                    img = np.load(f)
                    rec["server_frame_md5"] = hashlib.md5(img.tobytes()).hexdigest()
                    rec["same_pixels_as_server"] = rec["server_frame_md5"] == rec["own_decode_md5"]
                    rec["pose_on_server_frame"] = pose_json(model, img)
            report["frames"][key] = rec
            print(key, "디코드 md5", rec["own_decode_md5"][:8], "사람", rec["own_decode_pose"]["n"], "dtype", rec["own_decode_pose"]["dtype"], flush=True)
    (out / f"probe_{a.mode}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("끝 →", out / f"probe_{a.mode}.json")


if __name__ == "__main__":
    main()
