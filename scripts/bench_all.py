# -*- coding: utf-8 -*-
"""항목별 추론 속도를 (.pt | ONNX) × (CPU | GPU) 2×2 로 잰다.

왜: 배포 대상이 퀄컴 NPU 라 서버 GPU 의 PyTorch 수치만으로는 판단할 수 없다.
    ONNX-CPU 가 엣지에 가장 가까운 대리 지표이고, 해상도를 올릴 때 몇 배가 되는지는
    장치가 달라도 대체로 옮겨간다. 시험은 RTSP 실시간이라 표본 주기를 못 지키면 점수가 무너진다.

한 표본 = 그 항목이 0.5초(쓰러짐은 0.1초)마다 실제로 돌리는 뷰 전부(방화 6뷰·침입 9타일).
여유 = 표본 주기 / 실제 소요. 1.0 미만이면 실시간 불가.

출력: dumps/bench_all.json · 표 형태로 출력
사용: python bench_all.py [--items 쓰러짐,배회] [--skip-cpu-onnx]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_paths as KP           # noqa: E402
import kisa_items as K            # noqa: E402

OUT = V / "dumps/bench_all.json"
EXP = V / "dumps/onnx"

# 항목 → (가중치, 표본 주기 초, 뷰 수, 해상도들)
PLAN = {
    "쓰러짐": (str(KP.V / "model/yolo11x-pose.pt"), 0.1, 1, (640, 960)),
    "배회": ("person_v2.pt", 0.5, 1, (640, 960)),
    "방화": ("fire_snowfull.pt", 0.5, 6, (640, 960)),
    "침입": ("person_v3.pt", 0.5, 9, (960,)),
}


def frame_of(item):
    mp4 = next(iter(sorted(KP.videos(item).glob("*.mp4"))), None)
    if not mp4:
        return np.zeros((720, 1280, 3), np.uint8)
    cap = cv2.VideoCapture(str(mp4)); cap.set(cv2.CAP_PROP_POS_FRAMES, 300)
    ok, fr = cap.read(); cap.release()
    return fr if ok else np.zeros((720, 1280, 3), np.uint8)


def bench_pt(weights, frame, imgsz, device, views, n):
    from ultralytics import YOLO
    m = YOLO(str(weights))
    crops = [frame] * views
    for _ in range(3):
        m.predict(crops, imgsz=imgsz, conf=0.1, verbose=False, device=device)
    t0 = time.perf_counter()
    for _ in range(n):
        m.predict(crops, imgsz=imgsz, conf=0.1, verbose=False, device=device)
    return (time.perf_counter() - t0) / n * 1000.0


def onnx_path(weights, imgsz):
    EXP.mkdir(parents=True, exist_ok=True)
    dst = EXP / f"{Path(weights).stem}_{imgsz}.onnx"
    if not dst.is_file():
        from ultralytics import YOLO
        p = YOLO(str(weights)).export(format="onnx", imgsz=imgsz, opset=13, simplify=False, verbose=False)
        Path(p).replace(dst)
    return dst


def bench_onnx(path, imgsz, views, provider, n):
    import onnxruntime as ort
    so = ort.SessionOptions(); so.log_severity_level = 3
    sess = ort.InferenceSession(str(path), so, providers=[provider])
    name = sess.get_inputs()[0].name
    x = np.random.rand(views, 3, imgsz, imgsz).astype(np.float32)   # 뷰 수만큼 배치
    for _ in range(2):
        sess.run(None, {name: x})
    t0 = time.perf_counter()
    for _ in range(n):
        sess.run(None, {name: x})
    return (time.perf_counter() - t0) / n * 1000.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", default="쓰러짐,배회,방화,침입")
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    want = [x.strip() for x in a.items.split(",") if x.strip()]

    out = {}
    print(f"  {'항목':<6} {'해상도':<6} {'pt-GPU':>9} {'pt-CPU':>9} {'onnx-GPU':>10} {'onnx-CPU':>10}   여유(최저)")
    for item in want:
        if item not in PLAN:
            continue
        wname, stride, views, sizes = PLAN[item]
        w = K.WEIGHTS / wname
        if not w.is_file():
            print(f"  {item}: 가중치 없음"); continue
        fr = frame_of(item)
        budget = stride * 1000.0
        rows = []
        for z in sizes:
            cell = {}
            for key, fn in (("pt_gpu", lambda: bench_pt(w, fr, z, "0", views, a.n)),
                            ("pt_cpu", lambda: bench_pt(w, fr, z, "cpu", views, max(3, a.n // 3))),
                            ("onnx_gpu", lambda: bench_onnx(onnx_path(w, z), z, views,
                                                            "CUDAExecutionProvider", a.n)),
                            ("onnx_cpu", lambda: bench_onnx(onnx_path(w, z), z, views,
                                                            "CPUExecutionProvider", max(3, a.n // 3)))):
                try:
                    cell[key] = round(fn(), 1)
                except Exception as e:
                    cell[key] = None
                    print(f"    ({item} {z} {key} 실패: {type(e).__name__} {str(e)[:60]})", flush=True)
            vals = [v for v in cell.values() if v]
            cell.update(imgsz=z, views=views, budget_ms=budget,
                        headroom_min=round(budget / max(vals), 2) if vals else None)
            rows.append(cell)
            f = lambda k: f"{cell[k]:>9.1f}" if cell.get(k) else f"{'–':>9}"
            print(f"  {item:<6} {z:<6} {f('pt_gpu')} {f('pt_cpu')} {f('onnx_gpu'):>10} "
                  f"{f('onnx_cpu'):>10}   {cell['headroom_min']}배", flush=True)
        out[item] = {"stride_s": stride, "views": views, "rows": rows}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("저장 →", OUT)


if __name__ == "__main__":
    main()
