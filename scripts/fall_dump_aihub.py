# -*- coding: utf-8 -*-
"""AI허브 침입·쓰러짐 영상의 쓰러짐 35편을 배포 경로(자세 1280 + SeqNet)로 끝까지 돌려 곡선을 남긴다 = 학습에 안 쓴 외부 시험셋.

왜 (2026-09-20)
    쓰러짐 분류기의 학습 영상(연구개발 330편) 밖에서 규칙을 재 볼 영상이 채점 10편밖에 없었다.
    AI허브 쓰러짐 35편(야간 21)은 학습에 쓰지 않았고 사건 시작 프레임(event_frame)이 있다.
    정답 시각 = event_frame 시작 / fps. AI허브의 '사건 시작'은 넘어지기 시작하는 시각이라
    KISA 정의(머리가 바닥에 닿는 시각)보다 1초쯤 이를 수 있다. 창이 -2 ~ +10 초라 비교에는 쓸 수 있되
    여유 계산은 그만큼 보수적으로 본다. E02_017 은 사건이 1초에 시작해 '시작 무시' 규칙이면 반드시 놓친다(따로 본다).

출력: dumps/fall_seq_aihub35_1280/<편>.json  {imgsz, fps, gt, gt_end, tod, curves}
훑기: .venv/bin/python scripts/fall_sweep330.py dumps/fall_seq_aihub35_1280 [시작무시초]
사용: .venv/bin/python scripts/fall_dump_aihub.py [--imgsz 1280]   (GPU, 편당 1분 안팎)
"""
import argparse
import json
import sys
import time
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import fall_sweep as F  # noqa: E402  (dump_clip = 배포 FallJudge 를 끝까지 돌리는 도구)

SRC = V / "data/원본데이터/aihub_침입쓰러짐영상/쓰러짐"
OUT = V / "dumps/fall_seq_aihub35_1280"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--imgsz", type=int, default=1280)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mp4s = sorted(SRC.glob("*.mp4"))
    print(f"AI허브 쓰러짐 {len(mp4s)}편 · 자세 {a.imgsz} → {OUT}", flush=True)
    for i, mp4 in enumerate(mp4s, 1):
        out = OUT / (mp4.stem + ".json")
        if out.is_file():
            continue
        meta = json.loads(mp4.with_suffix(".json").read_text(encoding="utf-8"))
        t0 = time.time()
        F.dump_clip(mp4, a.imgsz, out)
        d = json.loads(out.read_text(encoding="utf-8"))
        ev = meta["annotations"]["event_frame"][0]
        d["gt"] = round(ev[0] / d["fps"], 2)
        d["gt_end"] = round(ev[1] / d["fps"], 2)
        d["tod"] = "Night" if meta["metadata"].get("night") else "Day"
        out.write_text(json.dumps(d), encoding="utf-8")
        print(f"  {i}/{len(mp4s)} {mp4.stem} 정답 {d['gt']}s {d['tod']} 트랙 {len(d['curves'])} {time.time() - t0:.0f}s", flush=True)
    print("끝. 훑기: .venv/bin/python scripts/fall_sweep330.py dumps/fall_seq_aihub35_1280", flush=True)


if __name__ == "__main__":
    main()
