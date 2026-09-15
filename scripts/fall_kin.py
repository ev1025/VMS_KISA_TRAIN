# -*- coding: utf-8 -*-
"""쓰러짐: 생체역학 특징(머리 수직 속도)으로 오탐과 진짜 낙상을 가른다.

배경(딥리서치): 발화 순간의 '정적 자세'로는 034(오검)와 153(정검)이 분리되지 않았다.
  오히려 오검이 더 누운 형상이었다. 의도적으로 눕는 동작과 낙상의 결정적 차이는
  '감속의 유무'다. 낙상은 머리가 중력으로 가속하며 떨어지고, 눕기는 스스로 속도를 줄인다.
  → 머리 Y좌표를 시간 미분한 수직 속도(HVV)를 사람 키로 정규화해 쓴다(스케일 불변).

주의: 이 파이프라인은 트랙이 끊긴 구간을 0벡터로 채운다. 속도 계산에 그대로 쓰면
  좌표가 원점으로 순간이동해 속도가 발산한다. 그래서 여기서는 0패딩을 쓰지 않고
  '실제로 관측된 프레임'만으로 속도를 구한다.

사용: python fall_kin.py dump   (10편 추론 → dumps/fall_kin.json)
      python fall_kin.py check  (미검·오검·정검의 HVV 분포 비교)
"""
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_paths as KP           # noqa: E402
import kisa_items as K            # noqa: E402

OUT = V / "dumps/fall_kin.json"
NOSE = 0
STRIDE = 0.1                      # 자세 추출 간격(10fps)


def gt_of(xml_path):
    al = ET.parse(xml_path).getroot().find(".//Alarm")
    if al is None:
        return None
    h, m, s = (al.findtext("StartTime") or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def head_and_height(kp):
    """(머리 y, 사람 세로높이). 관절이 부족하면 None. 화면 좌표라 y 가 클수록 아래다."""
    a = np.asarray(kp)
    pts = a[:, :2]
    ok = (pts[:, 0] > 0) | (pts[:, 1] > 0)
    p = pts[ok]
    if len(p) < 3:
        return None
    h = float(np.ptp(p[:, 1]))
    w = float(np.ptp(p[:, 0]))
    nose_y = float(a[NOSE][1]) if a[NOSE][1] > 0 else float(p[:, 1].min())
    size = max(math.hypot(w, h), 1.0)      # 사람 크기(대각). 거리에 따른 스케일을 없앤다
    return nose_y, size


def dump():
    cfg = K.ITEMS["falldown"]
    out = {}
    for mp4 in sorted(KP.videos("쓰러짐").glob("*.mp4")):
        judge = K.FallJudge(K.WEIGHTS / cfg["model"], K.WEIGHTS / "fall_track.pt", 1.1, cfg["need"])
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

        tracks = []
        for tr in judge.tracks:
            # 실제로 관측된 프레임만 쓴다(0패딩 제외) → 속도 발산을 막는다
            obs = []
            for fi in sorted(tr["frames"]):
                hh = head_and_height(tr["frames"][fi])
                if hh:
                    obs.append([round(fi * STRIDE, 2), round(hh[0], 1), round(hh[1], 1)])
            if len(obs) < 3:
                continue
            tracks.append({"obs": obs, "curve": tr.get("curve") or []})
        out[mp4.stem] = {"gt": gt_of(mp4.with_suffix(".xml")), "tracks": tracks}
        print(f"  {mp4.stem}: 트랙 {len(tracks)}개 · GT {out[mp4.stem]['gt']}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print("저장 →", OUT)


def max_hvv(obs, t0, t1):
    """[t0,t1] 구간의 최대 하강 속도. 사람 크기로 나눠 거리와 무관하게 만든다(단위: 크기/초).
       화면 y 는 아래로 갈수록 크므로 (y증가)=하강. 관측 간격이 벌어진 구간은 건너뛴다."""
    best = 0.0
    for a, b in zip(obs, obs[1:]):
        dt = b[0] - a[0]
        if dt <= 0 or dt > 0.5:            # 0.5초 넘게 끊긴 구간은 속도로 보지 않는다
            continue
        if not (t0 <= b[0] <= t1):
            continue
        v = (b[1] - a[1]) / dt / max(b[2], 1.0)
        best = max(best, v)
    return best


def check():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    th, need = K.ITEMS["falldown"]["th"], K.ITEMS["falldown"]["need"]
    print("  클립별: 정답 부근(GT-3~GT+3) 최대 하강속도 vs 발화 부근 최대 하강속도")
    print("  (단위 = 사람크기/초. 낙상이면 크고, 천천히 눕기면 작아야 한다)")
    for stem, v in sorted(data.items()):
        gt = v["gt"]
        # 실제 발화 시각 재현
        fired = None
        for tr in v["tracks"]:
            run = 0
            for i, (t, z) in enumerate(tr["curve"]):
                p = 1.0 / (1.0 + math.exp(-z))
                run = run + 1 if p >= th else 0
                if run >= need:
                    ft = tr["curve"][i - need + 1][0]
                    fired = ft if fired is None else min(fired, ft)
                    break
        near_gt = max((max_hvv(tr["obs"], gt - 3, gt + 3) for tr in v["tracks"]), default=0.0)
        near_fire = max((max_hvv(tr["obs"], fired - 3, fired + 3) for tr in v["tracks"]),
                        default=0.0) if fired is not None else 0.0
        verdict = ("정검" if fired is not None and gt - 2 <= fired <= gt + 10
                   else ("미검" if fired is None else "오검"))
        print(f"    {stem[4:]:<12} {verdict}  GT {gt:>4}  발화 {('%.1f' % fired) if fired else '없음':>7}  "
              f"정답부근HVV {near_gt:6.3f}  발화부근HVV {near_fire:6.3f}")


if __name__ == "__main__":
    (dump if sys.argv[1] == "dump" else check)()
