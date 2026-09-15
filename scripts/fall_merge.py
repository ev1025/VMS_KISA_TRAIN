# -*- coding: utf-8 -*-
"""쓰러짐: 분절된 트랙의 점수를 병합해 재채점한다.

배경: 미검 클립에서 한 사람이 여러 트랙으로 쪼개져 점수가 0.238 / 0.132 / 0.062 로 나뉘었다.
      문턱(0.269)은 트랙 하나가 단독으로 넘어야 해서, 쪼개지면 영영 못 넘는다.
방법: 같은 시각에 공간적으로 가까운 트랙끼리 묶어 그 시점 점수를 최댓값으로 올린다(평균은 희석됨).
      트랙을 새로 잇는 게 아니라 점수만 올리므로 추론을 다시 하지 않아도 된다.
      먼 곳의 다른 사람이 섞이지 않게 거리 조건을 둔다.

1단계(dump): 10편을 한 번 추론해 창마다 (시각, 로짓, 중심x, 중심y, 사람크기) 를 저장
2단계(sweep): 병합 거리 × 문턱 × 연속 을 훑어 F1 비교
사용: python fall_merge.py dump | sweep
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

OUT = V / "dumps/fall_tracks.json"
BEFORE, AFTER = 2.0, 10.0


def gt_of(xml_path):
    al = ET.parse(xml_path).getroot().find(".//Alarm")
    if al is None:
        return None
    h, m, s = (al.findtext("StartTime") or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def kp_extent(kp):
    """관절 좌표에서 사람 크기(대각 길이) 추정. 병합 거리 기준을 사람 크기에 비례시키려는 것."""
    try:
        pts = np.asarray(kp)[:, :2]
        pts = pts[(pts[:, 0] > 0) | (pts[:, 1] > 0)]
        if len(pts) < 2:
            return None
        return float(math.hypot(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])))
    except Exception as e:
        print("  자세 계산 실패:", type(e).__name__, e, flush=True)
        return None


def dump():
    cfg = K.ITEMS["falldown"]
    out = {}
    for mp4 in sorted(KP.videos("쓰러짐").glob("*.mp4")):
        judge = K.FallJudge(K.WEIGHTS / cfg["model"], K.WEIGHTS / "fall_track.pt",
                            1.1, cfg["need"])          # 발화 막고 전 구간 평가
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps * cfg["stride"]))
        seen = {}                                      # 트랙별 이미 기록한 창 수
        rec = {}                                       # 트랙별 [(t, z, cx, cy, size)]
        i = 0
        while True:
            if not cap.grab():
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    judge.feed(i / fps, fr)
                    # feed 안에서 창이 추가된 트랙을 찾아 그 시점 위치를 같이 기록한다
                    for k, tr in enumerate(judge.tracks):
                        cur = tr.get("curve") or []
                        if len(cur) > seen.get(k, 0):
                            seen[k] = len(cur)
                            t, z = cur[-1]
                            cx, cy = tr["last_c"]
                            kp = tr["frames"].get(tr["last_i"])
                            rec.setdefault(k, []).append(
                                [round(t, 2), round(z, 3), round(float(cx), 1),
                                 round(float(cy), 1), round(kp_extent(kp) or 0.0, 1)])
            i += 1
        cap.release()
        out[mp4.stem] = {"gt": gt_of(mp4.with_suffix(".xml")),
                         "tracks": [v for v in rec.values() if v]}
        print(f"  {mp4.stem}: 트랙 {len(out[mp4.stem]['tracks'])}개 · GT {out[mp4.stem]['gt']}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print("저장 →", OUT)


def merged_onset(tracks, th, need, ratio):
    """같은 시각의 가까운 트랙끼리 점수를 최댓값으로 올린 뒤, 트랙별 연속 돌파를 본다.
       ratio = 병합 허용 거리 / 사람 크기. 0 이면 병합하지 않음(현재 동작)."""
    # 시각별 (중심, 크기, p) 목록
    at = {}
    for tr in tracks:
        for t, z, cx, cy, sz in tr:
            at.setdefault(round(t, 2), []).append((cx, cy, sz, 1.0 / (1.0 + math.exp(-z))))
    best = None
    for tr in tracks:
        run = 0
        for idx, (t, z, cx, cy, sz) in enumerate(tr):
            p = 1.0 / (1.0 + math.exp(-z))
            if ratio > 0:
                lim = ratio * max(sz, 1.0)
                for ox, oy, osz, op in at.get(round(t, 2), []):
                    if op > p and math.hypot(cx - ox, cy - oy) <= lim:
                        p = op                      # 가까운 트랙의 더 높은 점수를 취한다
            run = run + 1 if p >= th else 0
            if run >= need:
                t0 = tr[idx - need + 1][0]
                best = t0 if best is None else min(best, t0)
                break
    return best


def score(data, th, need, ratio):
    tp = fn = fp = 0
    miss = []
    for stem, d in data.items():
        gt, sa = d["gt"], merged_onset(d["tracks"], th, need, ratio)
        if sa is None:
            fn += 1; miss.append(stem)
        elif gt is not None and gt - BEFORE <= sa <= gt + AFTER:
            tp += 1
        else:
            fp += 1; fn += 1; miss.append(stem)
    r = tp / (tp + fn) if tp + fn else 0.0
    p = tp / (tp + fp) if tp + fp else 0.0
    return (2 * r * p / (r + p) * 100 if r + p else 0.0), tp, fn, fp, miss


def sweep():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cfg = K.ITEMS["falldown"]
    base = score(data, cfg["th"], cfg["need"], 0.0)
    print(f"  기준(병합 없음) th={cfg['th']} need={cfg['need']} → F1 {base[0]:.2f} "
          f"({base[1]}/{base[2]}/{base[3]}) 미검 {','.join(m[4:] for m in base[4])}")
    rows = []
    for ratio in (0.3, 0.5, 0.8, 1.0, 1.5):
        for need in (3, 4, 5):
            for i in range(15, 41):
                th = i / 100.0
                f1, tp, fn, fp, miss = score(data, th, need, ratio)
                rows.append((f1, ratio, th, need, tp, fn, fp, miss))
    rows.sort(key=lambda x: (-x[0], -x[2]))
    print("  병합 적용 상위:")
    seen = set()
    for f1, ratio, th, need, tp, fn, fp, miss in rows:
        key = (tp, fn, fp)
        if key in seen:
            continue
        seen.add(key)
        print(f"    F1 {f1:6.2f}  병합거리={ratio}x  th={th:.2f} need={need}  "
              f"{tp}/{fn}/{fp}  미검 {','.join(m[4:] for m in miss)}")
        if len(seen) >= 6:
            break


if __name__ == "__main__":
    (dump if sys.argv[1] == "dump" else sweep)()
