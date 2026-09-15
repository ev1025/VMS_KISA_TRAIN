# -*- coding: utf-8 -*-
"""채점 전용 검증셋(evalset_<mode>)으로 가중치의 mAP 를 잰다 → results/<실험>/eval_map.json
검증셋은 build_evalset.py 가 만든 것(배포 검증영상의 손라벨·전파 결과 + 발생 전 배경). 학습에는 절대 안 들어간다.
사용: python scripts/eval_map.py fire --exp <실험명> [--pt 경로]   (pt 생략 시 runs/<실험>/<model>/weights/best.pt)
      python scripts/eval_map.py fire --all        (results/ 아래 meta.json 있는 실험 전부, eval_map.json 없는 것만)"""
import sys, io, json, argparse, time, os
from pathlib import Path
import kisa_paths as KP            # 저장소 루트는 여기 한 곳에서만 정의한다
V = KP.V
ap = argparse.ArgumentParser(); ap.add_argument("mode", choices=["fire", "person"])
ap.add_argument("--exp"); ap.add_argument("--pt"); ap.add_argument("--all", action="store_true"); ap.add_argument("--force", action="store_true")
ap.add_argument("--imgsz", type=int, default=640); ap.add_argument("--batch", type=int, default=16); ap.add_argument("--device", default="0")
a = ap.parse_args()
DATA = V / "data/학습데이터" / f"evalset_{a.mode}" / "data.yaml"
if not DATA.exists():
    sys.exit(f"검증셋 없음: {DATA} (먼저 python scripts/build_evalset.py {a.mode})")
emeta = json.load(io.open(DATA.parent / "meta.json", encoding="utf-8")) if (DATA.parent / "meta.json").exists() else {}


def best_pt(name, meta):
    for c in (V / "runs" / name / str(meta.get("model", "")) / "weights/best.pt", V / "runs" / name / "weights/best.pt"):
        if c.is_file():
            return c
    return None


def run_one(name, pt):
    from ultralytics import YOLO
    m = YOLO(str(pt))
    r = m.val(data=str(DATA), imgsz=a.imgsz, batch=a.batch, device=a.device, plots=False, verbose=False, workers=4, project=str(V / "runs/_eval"), name=name, exist_ok=True)
    b = r.box
    out = {"exp": name, "pt": str(pt), "evalset": DATA.parent.name, "n_frames": emeta.get("frames"), "clips": len(emeta.get("clips", [])) if isinstance(emeta.get("clips"), list) else emeta.get("clips"),
           "map50": round(float(b.map50), 4), "map5095": round(float(b.map), 4), "P": round(float(b.mp), 4), "R": round(float(b.mr), 4),
           "per_class_map50": {str(k): round(float(v), 4) for k, v in zip(m.names.values(), b.ap50)} if len(b.ap50) == len(m.names) else None,
           "imgsz": a.imgsz, "measured": time.strftime("%F %T", time.gmtime(time.time() + 9 * 3600)) + " KST"}
    rdir = V / "results" / name; rdir.mkdir(parents=True, exist_ok=True)
    io.open(rdir / "eval_map.json", "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{name}: mAP50 {out['map50']} · mAP50-95 {out['map5095']} · P {out['P']} · R {out['R']}  ({out['n_frames']}프레임)")
    return out


if a.all:
    for md in sorted((V / "results").glob("*/meta.json")):
        meta = json.load(io.open(md, encoding="utf-8"))
        if meta.get("item", "방화") != ("방화" if a.mode == "fire" else meta.get("item")):
            continue
        if (md.parent / "eval_map.json").exists() and not a.force:
            continue
        pt = best_pt(md.parent.name, meta)
        if not pt:
            print(f"{md.parent.name}: best.pt 없음"); continue
        try:
            run_one(md.parent.name, pt)
        except Exception as e:
            print(f"{md.parent.name}: 실패 {e}")
else:
    if not a.exp:
        sys.exit("--exp 또는 --all")
    meta = json.load(io.open(V / "results" / a.exp / "meta.json", encoding="utf-8")) if (V / "results" / a.exp / "meta.json").exists() else {}
    pt = Path(a.pt) if a.pt else best_pt(a.exp, meta)
    if not pt or not Path(pt).is_file():
        sys.exit(f"가중치 없음: {pt}")
    run_one(a.exp, pt)
