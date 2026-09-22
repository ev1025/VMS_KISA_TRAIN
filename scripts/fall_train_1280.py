# -*- coding: utf-8 -*-
"""쓰러짐 분류기(SeqNet)를 자세 1280 피처로 다시 학습한다(2026-09-20). 배포 fall_track.pt 는 640 피처로 배운 것이라 배포(1280)와 어긋나 있었다.

왜
    같은 6겹 교차검증에서 640 피처 87.3(오검 26) → 1280 피처 95.9(오검 2). 학습·추론 해상도를 맞추는 것이 오늘 본 것 중 가장 큰 개선이다.
    시드 5 앙상블은 1280 에서 +0.2 뿐이라 단일 모델로 간다(판정기 코드 변경 없음).

무엇을 하나
    1) feats/fall_kpts_1280 의 연구개발 330편으로 기본 레시피(fall_track.py main 과 동일: 대표 트랙 양성, 음성 3배, 12 epoch, AdamW 1e-3) 학습
       → runs/fall_track_1280/fall_track_1280.pt  (배포 파일은 덮지 않는다)
    2) 채점 견본 10편을 배포 판정기(FallJudge, 자세 1280) 그대로 돌려 곡선 덤프 → dumps/fall_seq_1280_net1280/  (fall_sweep330 으로 훑을 수 있다)
    3) 지금 규칙(ITEMS th·need·delay)으로 10편 점수 출력. 옛 분류기 곡선(dumps/fall_seq_1280_20260920)과 편별 대조.

사용
    .venv/bin/python scripts/fall_train_1280.py [--seed 0] [--device cuda] [--skip-train]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import torch

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import fall_track as FT          # noqa: E402
import fall_cv330 as CV          # noqa: E402  (prep · clip_windows · train · curves_of 재사용)
import fall_sweep as F           # noqa: E402
import kisa_items as K           # noqa: E402
import kisa_paths as KP          # noqa: E402

OUT_PT = V / "runs/fall_track_1280/fall_track_1280.pt"
OUT_DUMP = V / "dumps/fall_seq_1280_net1280"
KPTS = V / "feats/fall_kpts_1280"


def dump_with(net_pt, mp4, out, imgsz=1280):
    """fall_sweep.dump_clip 과 같되 분류기 가중치를 바꿔 끼운다."""
    cfg = K.ITEMS["falldown"]
    judge = K.FallJudge(K.WEIGHTS / cfg["model"], net_pt, 1.1, cfg["need"], None, imgsz)   # th 1.1 = 발화 안 함 → 끝까지 쌓인다
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * cfg["stride"]))
    i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                judge.feed(i / fps, fr)
        i += 1
    cap.release()
    curves = [tr["curve"] for tr in judge.tracks if tr.get("curve")]
    out.write_text(json.dumps({"imgsz": imgsz, "fps": round(fps, 3), "net": str(net_pt), "curves": curves}), encoding="utf-8")
    return curves


def score(clips, th, need, delay):
    tp = fn = fp = 0; det = []
    for s, g, cur in clips:
        sa = F.fire_time(cur, th, need)
        if sa is None:
            fn += 1; det.append((s[4:], "미검", None)); continue
        sa += delay
        if g - 2 <= sa <= g + 10:
            tp += 1; det.append((s[4:], "정검", round(sa - g, 1)))
        else:
            fn += 1; fp += 1; det.append((s[4:], "오검", round(sa - g, 1)))
    return (200.0 * tp / (2 * tp + fn + fp) if tp else 0.0), tp, fn, fp, det


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--skip-train", action="store_true")
    a = ap.parse_args()
    CV.DEV = torch.device(a.device)
    OUT_PT.parent.mkdir(parents=True, exist_ok=True); OUT_DUMP.mkdir(parents=True, exist_ok=True)

    if not a.skip_train or not OUT_PT.is_file():
        files = sorted(p for p in KPTS.glob("*.npz") if not p.stem.startswith(FT.DEPLOY_PREFIX))
        print(f"학습 영상 {len(files)}편 (1280 피처) · 시드 {a.seed} · {a.device}", flush=True)
        t0 = time.time(); clips = CV.prep(files)
        win = {s: CV.clip_windows(gt, dur, trs) for s, gt, dur, trs in clips}
        pos = [w for c in clips for w in win[c[0]][0]]; neg = [w for c in clips for w in win[c[0]][1]]
        net, npos, nneg, loss = CV.train(pos, neg, a.seed)
        torch.save(net.state_dict(), OUT_PT)
        print(f"학습 끝 양성창 {npos} 음성창 {nneg} 마지막 loss {loss:.4f} {time.time() - t0:.0f}s → {OUT_PT}", flush=True)

    # 채점 견본 10편을 배포 판정기로 (새 분류기)
    cfg = K.ITEMS["falldown"]
    clips = []
    for mp4 in sorted(KP.videos("쓰러짐").rglob("*.mp4")):
        f = OUT_DUMP / (mp4.stem + ".json")
        if not f.is_file():
            t0 = time.time(); dump_with(OUT_PT, mp4, f)
            print(f"  {mp4.stem} 곡선 덤프 {time.time() - t0:.0f}s", flush=True)
        clips.append((mp4.stem, float(F.gt_of(mp4)), json.loads(f.read_text(encoding="utf-8"))["curves"]))
    old = []
    for s, g, _c in clips:
        f = V / "dumps/fall_seq_1280_20260920" / (s + ".json")
        old.append((s, g, json.loads(f.read_text(encoding="utf-8"))["curves"]) if f.is_file() else (s, g, []))
    print(f"\n채점 견본 10편 · 배포 판정기(자세 1280) · 규칙 {cfg['th']}·{cfg['need']}·지연 {cfg['delay']}")
    for name, cl in (("옛 분류기(640 학습)", old), ("새 분류기(1280 학습)", clips)):
        f1, tp, fn, fp, det = score(cl, cfg["th"], cfg["need"], cfg["delay"])
        print(f"  {name}: {f1:.2f} (정검 {tp} 미검 {fn} 오검 {fp})  편별(경보-정답): {det}")
    print("\n새 분류기 · 규칙 훑기(문턱 × 연속, 지연 %.1f):" % cfg["delay"])
    for th in (0.60, 0.70, 0.755, 0.80, 0.85, 0.90):
        line = "  %.3f" % th
        for need in (2, 3, 4, 5, 6, 7):
            f1, tp, fn, fp, _ = score(clips, th, need, cfg["delay"])
            line += "  n%d %6.2f(%d/%d/%d)" % (need, f1, tp, fn, fp)
        print(line)


if __name__ == "__main__":
    main()
