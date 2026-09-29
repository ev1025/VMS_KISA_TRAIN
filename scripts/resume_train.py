# -*- coding: utf-8 -*-
"""last.pt 에서 학습을 이어간다(에폭 진척 유지). 체크포인트에 저장된 학습 인자 중 cache/workers 만 바꿔 쓸 수 있다.
사용: python scripts/resume_train.py <last.pt> [--cache ram|False] [--workers N]
ultralytics resume 는 인자를 체크포인트에서 읽으므로, 바꾸려면 체크포인트의 train_args 를 고쳐야 한다(원본은 .bak 로 남김)."""
import argparse, os, shutil, sys, time
# model.py 와 같은 CUDA 메모리 설정(2026-09-26). 빠지면 재개한 판이 같은 batch 에서 VRAM 을 약 10GB 더 잡았다(77 -> 87GB)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
from pathlib import Path
import torch

ap = argparse.ArgumentParser()
ap.add_argument("last")
ap.add_argument("--cache", default=None, help="ram | disk | False")
ap.add_argument("--workers", type=int, default=None)
ap.add_argument("--batch", type=int, default=None, help="배치 크기. 체크포인트가 OOM 등으로 줄어든 값(32)을 갖고 있으면 레시피 값으로 되돌린다")
a = ap.parse_args()
last = Path(a.last)
if not last.is_file():
    print(f"[resume] last.pt 없음: {last}"); sys.exit(2)

ck = torch.load(str(last), map_location="cpu", weights_only=False)
ta = ck.get("train_args") or {}
changed = {}
if a.cache is not None:
    v = False if str(a.cache).lower() in ("false", "0", "none", "") else a.cache
    if ta.get("cache") != v:
        ta["cache"] = v; changed["cache"] = v
if a.workers is not None and ta.get("workers") != a.workers:
    ta["workers"] = a.workers; changed["workers"] = a.workers
if a.batch is not None and ta.get("batch") != a.batch:
    ta["batch"] = a.batch; changed["batch"] = a.batch
print(f"[resume] {last} 에폭 {ck.get('epoch')} 까지 학습됨 · 인자 변경 {changed or '없음'}", flush=True)
if changed:
    bak = last.with_suffix(".pt.bak_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copy2(last, bak)                       # 원본 보존
    ck["train_args"] = ta
    torch.save(ck, str(last))
    print(f"[resume] 체크포인트 인자 갱신, 원본 → {bak.name}", flush=True)
del ck

from ultralytics import YOLO
YOLO(str(last)).train(resume=True)
print("[resume] 완료", flush=True)
