# -*- coding: utf-8 -*-
"""쓰러짐 배포 경로의 '입력 흔들림 민감도' 를 잰다(2026-09-20 밤 → 09-21).

왜
    같은 편을 서버(OpenCV 5.0)·토르 OpenCV 4.11·토르 PyAV 로 디코드하면 픽셀이 평균 0.5~1.3 단계 다르고, 그 차이만으로 견본 10편 점수가 100 / 84 / 80 으로 갈렸다.
    원인은 conf 0.10 근처 검출 → 그리디 추적 → 10초 창의 연쇄 증폭. "장비 맞추기" 대신 "픽셀 흔들림에도 경보가 안 바뀌는 파이프라인" 을 목표로 잡고
    서버 한 곳에서 흔들림을 흉내 내어 재는 잣대다.

흔들림 종류(--perturb, 쉼표로 여러 개)
    off+1 / off+2 / off-1   전 픽셀 균일 밝기 이동(토르 OpenCV 4.11 의 +1.25 편향 흉내). 1차 결과: 옛 분류기는 이것엔 안 흔들렸다(10편 전부 그대로).
    noise50 / noise100      픽셀의 50% / 100% 에 ±1 무작위(프레임 번호로 결정적). 토르 PyAV 의 '절반 픽셀 ±1' 반올림 무늬 흉내.
    off0                    흔들림 없음(기준)
전처리(--blur N, 0 = 없음): 자세 모델에 넣기 전 N×N 가우시안 블러. 반올림 무늬를 지워 디코더 간 차이에 둔감하게 하는 후보.

사용
    .venv/bin/python scripts/fall_perturb.py --tag old_c10_noise --pose-conf 0.10 --perturb off0,noise50,noise100 [--blur 3] [--net ...] [--imgsz 1280]
    결과: dumps/fall_perturb/<tag>/<흔들림>/<편>.json + 요약표(판정이 바뀌는 편 수)
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
import fall_sweep as F      # noqa: E402
import kisa_items as K      # noqa: E402
import kisa_paths as KP     # noqa: E402


def perturb(fr, spec, frame_idx):
    if spec == "off0":
        return fr
    if spec.startswith("off"):
        v = int(spec[3:])
        return cv2.add(fr, np.full_like(fr, v)) if v > 0 else cv2.subtract(fr, np.full_like(fr, -v))
    if spec.startswith("noise"):
        frac = int(spec[5:]) / 100.0
        rng = np.random.default_rng(frame_idx)                       # 프레임마다 다른, 그러나 재현되는 무늬
        mask = rng.random(fr.shape[:2]) < frac
        sign = rng.integers(0, 2, fr.shape[:2]).astype(np.int16) * 2 - 1
        d = (mask * sign).astype(np.int16)[..., None]
        return np.clip(fr.astype(np.int16) + d, 0, 255).astype(np.uint8)
    raise SystemExit("모르는 흔들림: " + spec)


def run_clip(mp4, net_pt, pose_conf, imgsz, spec, blur):
    cfg = K.ITEMS["falldown"]
    nets = [Path(x) for x in str(net_pt).split(",")] if "," in str(net_pt) else net_pt      # 쉼표면 앙상블(로짓 평균, 2026-09-21)
    judge = K.FallJudge(K.WEIGHTS / cfg["model"], nets, 1.1, cfg["need"], None, imgsz, pose_conf=pose_conf)
    cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps * cfg["stride"])); i = 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if ok:
                fr = perturb(fr, spec, i)
                if blur:
                    fr = cv2.GaussianBlur(fr, (blur, blur), 0)
                judge.feed(i / fps, fr)
        i += 1
    cap.release()
    return [tr["curve"] for tr in judge.tracks if tr.get("curve")], fps


def verdict(curves, gt, th, need, delay):
    sa = F.fire_time(curves, th, need)
    if sa is None:
        return "미검", None
    sa += delay
    return ("정검" if gt - 2 <= sa <= gt + 10 else "오검"), round(sa - gt, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--pose-conf", type=float, default=0.10)
    ap.add_argument("--net", default=str(K.WEIGHTS / "fall_track.pt"), help="분류기 가중치. 쉼표로 여러 개면 로짓 평균 앙상블")
    ap.add_argument("--perturb", default="off0,off+1,off+2,off-1")
    ap.add_argument("--blur", type=int, default=0)
    ap.add_argument("--imgsz", type=int, default=1280)
    a = ap.parse_args()
    cfg = K.ITEMS["falldown"]; th, need, delay = cfg["th"], cfg["need"], float(cfg.get("delay", 0.0))
    specs = a.perturb.split(",")
    root = V / "dumps/fall_perturb" / a.tag
    mp4s = sorted(KP.videos("쓰러짐").rglob("*.mp4"))
    print(f"[{a.tag}] 자세 conf {a.pose_conf} · 분류기 {a.net} · 블러 {a.blur} · 흔들림 {specs} · {len(mp4s)}편", flush=True)
    table = {}
    for spec in specs:
        od = root / spec; od.mkdir(parents=True, exist_ok=True)
        for mp4 in mp4s:
            f = od / (mp4.stem + ".json")
            if not f.is_file():
                t0 = time.time(); curves, fps = run_clip(mp4, a.net, a.pose_conf, a.imgsz, spec, a.blur)
                f.write_text(json.dumps({"imgsz": a.imgsz, "fps": round(fps, 3), "perturb": spec, "blur": a.blur, "pose_conf": a.pose_conf, "net": a.net, "curves": curves}), encoding="utf-8")
                print(f"  {spec} {mp4.stem} 트랙 {len(curves)} {time.time() - t0:.0f}s", flush=True)
            d = json.loads(f.read_text(encoding="utf-8"))
            table.setdefault(mp4.stem, {})[spec] = verdict(d["curves"], float(F.gt_of(mp4)), th, need, delay)
    print(f"\n[{a.tag}] 규칙 {th}·{need}·지연 {delay} · 블러 {a.blur} · 편별 판정(경보-정답 초) · 흔들림 {specs}")
    unstable = 0; scores = {}
    for stem, row in table.items():
        vs = [row[s][0] for s in specs]
        flag = "  <- 흔들림에 바뀜" if len(set(vs)) > 1 else ""
        unstable += bool(flag)
        print("  %-13s " % stem[4:] + "  ".join("%s:%s%s" % (s, row[s][0], "" if row[s][1] is None else "(%+.1f)" % row[s][1]) for s in specs) + flag)
    for s in specs:
        tp = sum(1 for r in table.values() if r[s][0] == "정검"); fn = sum(1 for r in table.values() if r[s][0] != "정검"); fp = sum(1 for r in table.values() if r[s][0] == "오검")
        scores[s] = 200.0 * tp / (2 * tp + fn + fp) if tp else 0.0
    print("  점수: " + "  ".join("%s → %.2f" % (s, scores[s]) for s in specs) + f"   |  판정이 바뀌는 편 {unstable}/{len(table)}")


if __name__ == "__main__":
    main()
