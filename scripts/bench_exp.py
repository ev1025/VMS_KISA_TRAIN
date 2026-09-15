# -*- coding: utf-8 -*-
"""실험별 추론 속도 → results/<실험>/bench.json

재는 조합: (.pt | ONNX) x (GPU | CPU). 실험마다 모델과 해상도가 달라 속도가 크게 갈린다.
한 표본 = 그 항목이 주기마다 실제로 돌리는 뷰 전부(방화 6뷰 · 침입 9타일 · 배회·쓰러짐 1뷰).
여유 = 표본 주기 ÷ 소요. ONNX 는 (모델, 해상도)마다 따로 내보내 dumps/onnx_exp 에 둔다.

사용: python bench_exp.py [--only 이름조각] [--force] [--no-onnx]
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP           # noqa: E402

ITEM = {"방화": (0.5, 6), "침입": (0.5, 9), "배회": (0.5, 1), "쓰러짐": (0.1, 1), "사람": (0.5, 1)}
EXP_ONNX = V / "dumps/onnx_exp"


def frame_of(item):
    try:
        mp4 = next(iter(sorted(KP.videos(item if item in KP.ITEM_DIR else "방화").glob("*.mp4"))), None)
        cap = cv2.VideoCapture(str(mp4)); cap.set(cv2.CAP_PROP_POS_FRAMES, 300)
        ok, fr = cap.read(); cap.release()
        if ok:
            return fr
    except Exception:
        pass
    return np.zeros((720, 1280, 3), np.uint8)


def bench_pt(pt, frame, imgsz, views, device, n):
    from ultralytics import YOLO
    m = YOLO(str(pt))
    crops = [frame] * views
    for _ in range(3):
        m.predict(crops, imgsz=imgsz, conf=0.1, verbose=False, device=device)
    t0 = time.perf_counter()
    for _ in range(n):
        m.predict(crops, imgsz=imgsz, conf=0.1, verbose=False, device=device)
    return round((time.perf_counter() - t0) / n * 1000.0, 1)


def onnx_of(exp, pt, imgsz):
    EXP_ONNX.mkdir(parents=True, exist_ok=True)
    dst = EXP_ONNX / f"{exp}_{imgsz}.onnx"
    if not dst.is_file():
        from ultralytics import YOLO
        p = YOLO(str(pt)).export(format="onnx", imgsz=imgsz, opset=13, simplify=False, verbose=False)
        Path(p).replace(dst)
    return dst


def bench_onnx(path, imgsz, views, provider, n):
    import onnxruntime as ort
    so = ort.SessionOptions(); so.log_severity_level = 3
    # 컨테이너에서 코어 수를 잘못 잡아 자동 설정이 3배 이상 느리다(실측 735ms vs 202ms) → 명시한다
    so.intra_op_num_threads = min(36, os.cpu_count() or 8)
    sess = ort.InferenceSession(str(path), so, providers=[provider])
    name = sess.get_inputs()[0].name
    x = np.random.rand(1, 3, imgsz, imgsz).astype(np.float32)
    for _ in range(2):
        sess.run(None, {name: x})
    t0 = time.perf_counter()
    for _ in range(n):
        sess.run(None, {name: x})
    return round((time.perf_counter() - t0) / n * 1000.0 * views, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-onnx", action="store_true")
    ap.add_argument("--n", type=int, default=6)
    a = ap.parse_args()

    cache, done = {}, 0
    for md in sorted((V / "results").glob("*/meta.json")):
        exp = md.parent.name
        if a.only and a.only not in exp:
            continue
        out = md.parent / "bench.json"
        if out.is_file() and not a.force:
            try:
                if json.loads(out.read_text(encoding="utf-8")).get("onnx_cpu") is not None:
                    continue                       # 4칸 다 있는 것은 건너뛴다
            except Exception:
                pass
        try:
            m = json.loads(md.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        pt = m.get("best_pt")
        if not pt or not Path(pt).is_file():
            continue
        item = m.get("item", "방화")
        stride, views = ITEM.get(item, (0.5, 1))
        imgsz = int((m.get("train") or {}).get("imgsz", KP.DEFAULT_IMGSZ))
        cache.setdefault(item, frame_of(item))
        rec = {"model": m.get("model"), "imgsz": imgsz, "views": views, "budget_ms": stride * 1000.0}

        for key, fn in (("pt_gpu", lambda: bench_pt(pt, cache[item], imgsz, views, "0", a.n)),
                        ("pt_cpu", lambda: bench_pt(pt, cache[item], imgsz, views, "cpu", max(2, a.n // 3)))):
            try:
                rec[key] = fn()
            except Exception as e:
                rec[key] = None
                print(f"  {exp} {key} 실패: {type(e).__name__} {str(e)[:50]}", flush=True)

        if not a.no_onnx:
            try:
                ox = onnx_of(exp, pt, imgsz)
                for key, prov, nn in (("onnx_gpu", "CUDAExecutionProvider", a.n),
                                      ("onnx_cpu", "CPUExecutionProvider", max(2, a.n // 3))):
                    try:
                        rec[key] = bench_onnx(ox, imgsz, views, prov, nn)
                    except Exception as e:
                        rec[key] = None
                        print(f"  {exp} {key} 실패: {type(e).__name__} {str(e)[:50]}", flush=True)
            except Exception as e:
                print(f"  {exp} onnx 내보내기 실패: {type(e).__name__} {str(e)[:50]}", flush=True)

        vals = [v for v in (rec.get("pt_gpu"), rec.get("pt_cpu"), rec.get("onnx_gpu"), rec.get("onnx_cpu")) if v]
        rec["headroom"] = round(rec["budget_ms"] / min(vals), 2) if vals else None   # 가장 빠른 경로 기준
        rec["measured"] = time.strftime("%F %T", time.gmtime(time.time() + 9 * 3600)) + " KST"
        out.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
        g = lambda k: f"{rec.get(k)}ms" if rec.get(k) else "–"
        print(f"  {exp:<30} {rec['model']:<8} {imgsz:<5} "
              f"pt {g('pt_gpu')}/{g('pt_cpu')} · onnx {g('onnx_gpu')}/{g('onnx_cpu')} · 여유 {rec['headroom']}배", flush=True)
    print(f"완료 {done}개")


if __name__ == "__main__":
    main()
