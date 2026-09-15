# -*- coding: utf-8 -*-
"""
model.py — 화재/연기 YOLO 모델 통합 CLI (학습·튜닝·비교·평가·변환).

데이터 준비(01~04) 이후 모델 작업은 전부 이 파일 하나로:
  python model.py train   --models yolov8m                              # 단일 학습(baseline)
  python model.py train   --models all                                  # 다종(8n/8s/5n/5s/5m) 학습+onnx
  python model.py tune    --model yolov8s --imgsz 640                    # Optuna HPO(proxy)
  python model.py train   --models yolov8s --hp configs/tune_best_yolov8s.yaml   # 튜닝 HP 재학습(lr 보정)
  python model.py compare                                               # 다종 비교표(csv+md)
  python model.py eval    --weights <best.pt>                           # 단일 상세평가(mAP+FAR)
  python model.py export  <best.pt>                                     # 배포용 onnx

기본 경로는 config.py(DATA_YAML, RUNS_DIR) 사용. 서버 등은 --data/--project/--device로 override.
"""
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")   # multi_scale 가변 크기로 예약 VRAM 폭증 방지
import os, sys, csv, time, argparse, shutil
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path
import config as C

# 모델 레지스트리(단일 출처): 내부명 -> 비교표 표시명.
# yolov8m은 이미 학습된 baseline이라 별도.
MODELS = {
    "yolov8n": "YOLOv8n", "yolov8s": "YOLOv8s",
    "yolov5nu": "YOLOv5n(u)", "yolov5su": "YOLOv5s(u)", "yolov5mu": "YOLOv5m(u)",
}
BASELINE = ("yolov8m", "YOLOv8m(기존)")   # (run폴더명, 표시명) 비교 기준
ALL_MODELS = list(MODELS)                            # train --models all 대상(5종)

# 화재/연기 도메인 기본 레시피 (불꽃: 상하반전 금지, 색왜곡 약하게, 막판 모자이크 off)
RECIPE = dict(flipud=0.0, fliplr=0.5, hsv_h=0.015, hsv_s=0.5, hsv_v=0.4,
              mosaic=1.0, close_mosaic=10, patience=30, cos_lr=True)


def _YOLO(w):
    from ultralytics import YOLO   # 무거우니 필요할 때만 import
    return YOLO(w)


def _base(name):
    """base 가중치는 model/pretrained/ 에서 쓴다. 없으면 이름만 넘겨 ultralytics 가 받게 둔다(cwd 오염)."""
    from pathlib import Path
    p = Path(__file__).resolve().parent / "model" / "pretrained" / f"{name}.pt"
    return str(p) if p.exists() else f"{name}.pt"


def export_one(pt, opset=12, dynamic=True, quiet=False):
    """best.pt -> 배포용 dynamic onnx (CPU export = 학습 GPU 안 건드림). 이미 있으면 재사용."""
    pt = Path(pt)
    out = pt.with_suffix(".onnx")
    if out.exists():
        if not quiet: print(f"  [onnx] 이미 있음 {out}")
        return out
    try:
        p = _YOLO(str(pt)).export(format="onnx", dynamic=dynamic, simplify=True, opset=opset, device="cpu")
        if not quiet: print(f"  [onnx] {p}")
        return p
    except Exception as e:
        print(f"  [onnx 실패] {e}")
        return None


# ---------------- train (단일/다종/HP재학습) ----------------
def cmd_train(a):
    hp = {}
    if a.hp:
        import yaml
        hp = yaml.safe_load(Path(a.hp).read_text(encoding="utf-8"))
        hp["lr0"], hp["lrf"] = a.lr0, a.lrf   # proxy(짧은ep) 튜닝은 lr을 낮게 편향 -> 검증된 값으로 오버라이드
        print(f"[HP] {a.hp} 적용 (box={hp.get('box')}, opt={hp.get('optimizer')}) + lr0={a.lr0}/lrf={a.lrf} 오버라이드")
    data    = a.data or str(C.DATA_YAML)
    project = a.project or str(C.RUNS_DIR)
    models  = ALL_MODELS if a.models == ["all"] else a.models

    results = []
    for name in models:
        out = Path(project) / name / "weights" / "best.pt"
        if out.exists() and not a.force:
            print(f"[건너뜀] {name}: 이미 있음 ({out})")
            if not a.no_export: export_one(out)
            results.append((name, True, 0.0)); continue

        kw = dict(RECIPE, box=a.box); kw.update(hp)   # hp가 box/증강 등 덮어씀
        if a.cache: kw["cache"] = a.cache
        if a.workers is not None: kw["workers"] = a.workers
        for kv in a.extra:                      # k=v 문자열을 yaml 로 타입 변환
            import yaml; k, v = kv.split("=", 1); kw[k] = yaml.safe_load(v)
        print(f"\n{'='*56}\n[학습] {name} imgsz={a.imgsz} ep={a.epochs} batch={a.batch} dev={a.device} box={kw.get('box')}\n{'='*56}")
        t0 = time.time()
        try:
            _YOLO(_base(name)).train(data=data, project=project, name=name, exist_ok=True,
                                      imgsz=a.imgsz, epochs=a.epochs, batch=a.batch, device=a.device,
                                      **dict({"multi_scale": a.multi_scale}, **kw))   # --extra multi_scale=0.5 가 우선
            dt = time.time() - t0
            print(f"[완료] {name} {dt/60:.1f}분 -> {out}")
            if not a.no_export: export_one(out)
            results.append((name, True, dt))
        except Exception as e:                          # 한 모델 실패해도 나머지 진행
            print(f"[실패] {name}: {e}")
            results.append((name, False, time.time() - t0))

    print(f"\n{'='*56}\n[요약]")
    for n, ok, dt in results:
        print(f"  {n:14s} {'OK ' if ok else 'FAIL'} {dt/60:6.1f}분")
    done = sum(1 for _, ok, _ in results if ok)
    print(f"학습 {done}/{len(results)}. 다음: python model.py compare")


# ---------------- tune (Optuna HPO, proxy) ----------------
def cmd_tune(a):
    import optuna, yaml
    data = a.data or str(C.DATA_YAML)

    def objective(trial):
        # 유효 + 고가치 파라미터만 (fl_gamma 없음=YOLOv8 미지원, iou는 추론값이라 제외)
        hp = dict(
            lr0=trial.suggest_float("lr0", 1e-4, 2e-2, log=True),
            lrf=trial.suggest_float("lrf", 0.01, 0.3),
            momentum=trial.suggest_float("momentum", 0.85, 0.98),
            weight_decay=trial.suggest_float("weight_decay", 1e-5, 1e-3, log=True),
            warmup_epochs=trial.suggest_float("warmup_epochs", 0.0, 5.0),
            optimizer=trial.suggest_categorical("optimizer", ["SGD", "AdamW"]),
            box=trial.suggest_float("box", 5.0, 12.0),
            cls=trial.suggest_float("cls", 0.3, 1.0),
            dfl=trial.suggest_float("dfl", 1.0, 2.0),
            hsv_h=trial.suggest_float("hsv_h", 0.0, 0.03),
            hsv_s=trial.suggest_float("hsv_s", 0.3, 0.7),
            hsv_v=trial.suggest_float("hsv_v", 0.2, 0.5),
            degrees=trial.suggest_float("degrees", 0.0, 10.0),
            translate=trial.suggest_float("translate", 0.0, 0.2),
            scale=trial.suggest_float("scale", 0.3, 0.7),
            shear=trial.suggest_float("shear", 0.0, 2.0),
            mosaic=trial.suggest_float("mosaic", 0.7, 1.0),
            mixup=trial.suggest_float("mixup", 0.0, 0.2),
        )
        model = _YOLO(a.model if a.model.endswith(".pt") else a.model + ".pt")

        # 매 epoch fitness 보고 -> 나쁜 trial 가지치기 (단일 GPU에서만 동작)
        def on_fit_epoch_end(tr):
            fit = float(tr.fitness) if tr.fitness is not None else 0.0
            trial.report(fit, step=tr.epoch)
            if trial.should_prune():
                raise optuna.TrialPruned()
        model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

        model.train(data=data, imgsz=a.imgsz, epochs=a.epochs, device=a.device, fraction=a.fraction,
                    project=a.project or "runs_tune", name=f"trial_{trial.number}", exist_ok=True,
                    flipud=0.0, fliplr=0.5, close_mosaic=10, cos_lr=True, val=True, verbose=False, plots=False, **hp)
        return float(model.trainer.best_fitness)

    study_name = a.study or Path(a.model).stem
    study = optuna.create_study(
        direction="maximize", sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_warmup_steps=10),
        storage=f"sqlite:///tune_{study_name}.db", study_name=study_name, load_if_exists=True)
    study.optimize(objective, n_trials=a.trials, timeout=a.timeout or None)

    out = Path(f"tune_best_{study_name}.yaml")
    out.write_text(yaml.safe_dump(study.best_params, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"\n[완료] {study_name} best fitness={study.best_value:.4f} -> {out}")
    print(f"이식: python model.py train --models {Path(a.model).stem} --hp {out} --imgsz 1280")


# ---------------- compare (다종 비교표) ----------------
def cmd_compare(a):
    project = a.project or str(C.RUNS_DIR)
    data = a.data or str(C.DATA_YAML)
    # 레지스트리에서 파생(중복 제거) + baseline 추가
    cands = {disp: f"{project}/{name}/weights/best.pt" for name, disp in MODELS.items()}
    cands[BASELINE[1]] = f"{project}/{BASELINE[0]}/weights/best.pt"
    print(f"비교 시작 (imgsz={a.imgsz}, device={a.device})\n")
    rows = []
    for name, wp in cands.items():
        if not Path(wp).exists():
            print(f"  [없음] {name}: {wp}"); continue
        model = _YOLO(wp)
        m = model.val(data=data, imgsz=a.imgsz, device=a.device, verbose=False, plots=False)
        # 속도는 val이 측정한 ms/img 사용 (별도 predict 루프는 torch 2.11 inference-mode 충돌)
        ms = float(m.speed.get("inference", 0.0)); fps = 1000.0 / ms if ms else 0.0
        params = sum(p.numel() for p in model.model.parameters()) / 1e6
        rows.append({"model": name, "mAP50": round(float(m.box.map50), 4), "mAP50_95": round(float(m.box.map), 4),
                     "ms_per_img": round(ms, 1), "fps": round(fps, 1),
                     "params_M": round(params, 2), "size_MB": round(Path(wp).stat().st_size / 1e6, 1)})
        print(f"  [완료] {name:14s} mAP50={rows[-1]['mAP50']:.3f} mAP50-95={rows[-1]['mAP50_95']:.3f} {rows[-1]['fps']:.0f}fps")

    if not rows:
        print("측정된 모델 없음. 먼저 python model.py train --models all"); return

    cols = ["model", "mAP50", "mAP50_95", "ms_per_img", "fps", "params_M", "size_MB"]
    with open("model_comparison.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    print("\n| 모델 | mAP@50 | mAP@50-95 | ms/img | FPS | 파라미터(M) | 크기(MB) |")
    print("|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: -x["mAP50_95"]):
        print(f"| {r['model']} | {r['mAP50']:.3f} | {r['mAP50_95']:.3f} | "
              f"{r['ms_per_img']:.1f} | {r['fps']:.0f} | {r['params_M']:.1f} | {r['size_MB']:.1f} |")
    print("\n저장: model_comparison.csv")


# ---------------- eval (단일 상세평가: mAP + 경보 FAR) ----------------
def cmd_eval(a):
    import yaml
    from ultralytics.data.utils import img2label_paths   # 이미지경로 -> 라벨경로 (ultralytics 규칙 그대로)
    model = _YOLO(a.weights)
    data = a.data or str(C.DATA_YAML)
    dy = yaml.safe_load(Path(data).read_text(encoding="utf-8"))
    # 클래스 이름은 평가 대상 yaml 에서 읽는다(config.py 고정이면 사람 모델에서 IndexError)
    names = dy.get("names") or {}
    names = [names[i] for i in sorted(names)] if isinstance(names, dict) else list(names)
    # (A) 검출 지표
    run = Path(a.weights).parent.parent.name                       # runs/<run>/weights/best.pt -> <run>
    # project 를 안 주면 ultralytics 전역 settings 의 runs_dir(남의 폴더일 수 있음)로 저장된다
    m = model.val(data=data, imgsz=a.imgsz, device=a.device, conf=0.001,
                  project=a.project or str(C.RUNS_DIR), name=f"val_{run}", exist_ok=True)
    det = {"mAP50": float(m.box.map50), "mAP50-95": float(m.box.map),
           "per_class": {names[i]: {"AP50": float(m.box.ap50[i]), "P": float(m.box.p[i]), "R": float(m.box.r[i])}
                         for i in range(len(names))}}
    # (B) image-level 경보 지표 (정상=네거티브)
    # val 목록은 --data 의 yaml 에서 뽑는다 (서버/로컬 어디서 돌려도 동작. C.DATASET 고정이면 남의 머신에서 0장)
    vp = Path(dy.get("path", "")) / dy["val"]
    imgs = sorted(vp.glob("*.jpg")) if vp.is_dir() else [Path(s) for s in vp.read_text(encoding="utf-8").split()]
    lbls = img2label_paths([str(i) for i in imgs])
    TP = FP = FN = TN = 0
    for im, lp in zip(imgs, lbls):
        lbl = Path(lp)
        gt_pos = lbl.exists() and lbl.read_text(encoding="utf-8").strip() != ""
        res = model.predict(str(im), imgsz=a.imgsz, conf=a.conf, device=a.device, verbose=False)[0]
        pred_pos = len(res.boxes) > 0
        if gt_pos and pred_pos: TP += 1
        elif gt_pos: FN += 1
        elif pred_pos: FP += 1
        else: TN += 1
    prec = TP / (TP + FP) if TP + FP else 0.0
    rec  = TP / (TP + FN) if TP + FN else 0.0
    f1   = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    far  = FP / (FP + TN) if FP + TN else 0.0

    rp = C.WORK / f"eval_{run}.md"; L = []                          # run 이름별로 (여러 모델 평가시 덮어쓰기 방지)
    rp.parent.mkdir(parents=True, exist_ok=True)                   # work/ 없는 머신(서버)에서 저장 실패 방지
    L.append("# 화재/연기 검출 평가 리포트\n")
    L.append(f"weights: `{a.weights}`  |  conf(경보): {a.conf}\n")
    L.append("## (A) 검출 지표\n")
    L.append(f"- mAP@50: **{det['mAP50']:.3f}**, mAP@50-95: **{det['mAP50-95']:.3f}**\n")
    L.append("| 클래스 | AP50 | P | R |\n|---|---|---|---|")
    for c, v in det["per_class"].items():
        L.append(f"| {c} | {v['AP50']:.3f} | {v['P']:.3f} | {v['R']:.3f} |")
    L.append("\n## (B) 경보(image-level) 지표\n")
    L.append(f"- 검증 이미지 {len(imgs):,}장 (정상=네거티브 포함)\n")
    L.append("| | 예측 양성 | 예측 음성 |\n|---|---|---|")
    L.append(f"| 실제 양성(화재/연기) | TP={TP} | FN={FN} |")
    L.append(f"| 실제 음성(정상) | FP={FP} | TN={TN} |")
    L.append(f"\n- Precision **{prec:.3f}** / Recall **{rec:.3f}** / F1 **{f1:.3f}**")
    L.append(f"- 오탐율(FAR, 정상중 오경보) **{far:.3f}**")
    rp.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L)); print(f"\n[완료] 리포트: {rp}")


# ---------------- export (배포용 onnx) ----------------
def cmd_export(a):
    if not a.model or not Path(a.model).exists():
        print("사용법: python model.py export <best.pt 경로> [--static]"); sys.exit(1)
    p = export_one(a.model, opset=a.opset, dynamic=not a.static, quiet=False)
    if not p:
        return
    # 배포 ONNX 저장소(work/onnx_final)에 학습 run 이름으로 자동 보관 (단일 출처)
    reg = C.WORK / "onnx_final"; reg.mkdir(parents=True, exist_ok=True)
    run = Path(a.model).parent.parent.name          # runs/<run>/weights/best.pt -> <run>
    dst = reg / f"{run}{'_static' if a.static else ''}.onnx"
    shutil.copy2(p, dst)
    print(f"[완료] {p}\n  -> 저장소: {dst}\n  (Hailo 컴파일·배포는 저장소에서 갖다 씀)")


def _add_io(p, imgsz=1280):
    p.add_argument("--data", default="", help="data.yaml (기본 config.DATA_YAML)")
    p.add_argument("--project", default="", help="runs 경로 (기본 config.RUNS_DIR)")
    p.add_argument("--imgsz", type=int, default=imgsz)
    p.add_argument("--device", default="0")


def build():
    ap = argparse.ArgumentParser(description="화재/연기 YOLO 모델 통합 CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("train", help="학습 (단일/다종/HP 재학습)")
    t.add_argument("--models", nargs="+", default=["yolov8m"], help="모델명들 또는 'all'(8n/8s/5n/5s/5m)")
    t.add_argument("--hp", default="", help="HPO best yaml (있으면 적용 + lr 오버라이드)")
    t.add_argument("--lr0", type=float, default=0.01)
    t.add_argument("--lrf", type=float, default=0.01)
    t.add_argument("--box", type=float, default=7.5, help="box loss 가중(baseline yolov8m은 10)")
    t.add_argument("--cache", default="", help="ram|disk (Lustre 소파일 I/O 병목 회피)")
    t.add_argument("--workers", type=int, default=None, help="dataloader 워커 수(병렬 학습 시 CPU 분배)")
    t.add_argument("--extra", nargs="*", default=[], help="ultralytics train 인자 직접 전달 k=v (예: deterministic=False)")
    t.add_argument("--epochs", type=int, default=100)
    t.add_argument("--batch", type=int, default=-1, help="-1=AutoBatch, 서버 DDP는 32 등 고정")
    t.add_argument("--no-export", action="store_true", help="학습 후 onnx 자동변환 끔")
    t.add_argument("--force", action="store_true", help="best.pt 있어도 재학습")
    t.add_argument("--multi-scale", dest="multi_scale", action="store_true",
                   help="학습 중 입력 해상도를 ±50% 변주(추론 해상도 변경 내성)")
    _add_io(t); t.set_defaults(func=cmd_train)

    u = sub.add_parser("tune", help="Optuna HPO (proxy 튜닝)")
    u.add_argument("--model", default="yolov8s.pt")
    u.add_argument("--epochs", type=int, default=30)
    u.add_argument("--fraction", type=float, default=0.15, help="데이터 비율(proxy)")
    u.add_argument("--trials", type=int, default=30)
    u.add_argument("--timeout", type=int, default=0, help="초. 마감용 하드 타임아웃(0=무제한)")
    u.add_argument("--study", default="", help="study/db 이름(기본 모델명)")
    _add_io(u, imgsz=640); u.set_defaults(func=cmd_tune)

    c = sub.add_parser("compare", help="다종 비교표 (csv+md)")
    _add_io(c); c.set_defaults(func=cmd_compare)

    e = sub.add_parser("eval", help="단일 상세평가 (mAP + 경보 FAR)")
    e.add_argument("--weights", required=True)
    e.add_argument("--conf", type=float, default=0.25, help="경보 판정 임계값")
    _add_io(e); e.set_defaults(func=cmd_eval)

    x = sub.add_parser("export", help="배포용 onnx 변환")
    x.add_argument("model", nargs="?", default=os.environ.get("MODEL", ""))
    x.add_argument("--opset", type=int, default=12)
    x.add_argument("--static", action="store_true", help="고정 입력(기본 dynamic=640/1280 자유)")
    x.set_defaults(func=cmd_export)

    return ap


if __name__ == "__main__":
    args = build().parse_args()
    args.func(args)
