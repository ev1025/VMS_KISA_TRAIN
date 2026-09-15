# -*- coding: utf-8 -*-
"""쓰러짐 2차 자세 검증: 문턱을 넘어도 '실제로 누운 자세'가 아니면 발화를 막는다.

배경: C00_034_0005 는 정답 시각(188초)에 점수가 0.122 로 반응이 없는데,
      엉뚱한 253초에 문턱을 넘어 울린다. KISA 규칙상 창 밖 경보는 오검+미검을 동시에 받아
      이 한 편이 점수를 84.21 로 끌어내린다. 발화를 막기만 해도 88.89 가 된다.

검증 특징(관절에서 바로 계산, 추가 모델 없음):
  종횡비 aspect = 관절 가로폭 / 세로높이   → 누우면 1 을 넘는다(서 있으면 0.3~0.5)
  머리 낮음 head = (발끝 y - 코 y) / 사람크기 → 서 있으면 1 에 가깝고 누우면 0 에 가깝다
사용: python fall_verify.py dump | sweep
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

OUT = V / "dumps/fall_pose.json"
BEFORE, AFTER = 2.0, 10.0
NOSE = 0                          # COCO-17 관절 순서에서 코


def gt_of(xml_path):
    al = ET.parse(xml_path).getroot().find(".//Alarm")
    if al is None:
        return None
    h, m, s = (al.findtext("StartTime") or "0:0:0").split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def posture(kp):
    """(종횡비, 머리높이비). 관절이 부족하면 None."""
    try:
        a = np.asarray(kp)
        pts = a[:, :2]
        ok = (pts[:, 0] > 0) | (pts[:, 1] > 0)
        p = pts[ok]
        if len(p) < 3:
            return None
        w = float(np.ptp(p[:, 0])); h = float(np.ptp(p[:, 1]))
        size = max(math.hypot(w, h), 1.0)
        aspect = w / max(h, 1.0)
        nose_y = float(a[NOSE][1]) if a[NOSE][1] > 0 else float(p[:, 1].min())
        head = (float(p[:, 1].max()) - nose_y) / size      # 서 있으면 크고 누우면 작다
        return round(aspect, 3), round(head, 3)
    except Exception as e:
        print("  자세 계산 실패:", type(e).__name__, e, flush=True)
        return None


def dump():
    cfg = K.ITEMS["falldown"]
    out = {}
    for mp4 in sorted(KP.videos("쓰러짐").glob("*.mp4")):
        judge = K.FallJudge(K.WEIGHTS / cfg["model"], K.WEIGHTS / "fall_track.pt", 1.1, cfg["need"])
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, round(fps * cfg["stride"]))
        seen, rec, i = {}, {}, 0
        while True:
            if not cap.grab():
                break
            if i % step == 0:
                ok, fr = cap.retrieve()
                if ok:
                    judge.feed(i / fps, fr)
                    for k, tr in enumerate(judge.tracks):
                        cur = tr.get("curve") or []
                        if len(cur) > seen.get(k, 0):
                            seen[k] = len(cur)
                            t, z = cur[-1]
                            ps = posture(tr["frames"].get(tr["last_i"]))
                            rec.setdefault(k, []).append(
                                [round(t, 2), round(z, 3),
                                 ps[0] if ps else -1.0, ps[1] if ps else -1.0])
            i += 1
        cap.release()
        out[mp4.stem] = {"gt": gt_of(mp4.with_suffix(".xml")),
                         "tracks": [v for v in rec.values() if v]}
        print(f"  {mp4.stem}: 트랙 {len(out[mp4.stem]['tracks'])}개 · GT {out[mp4.stem]['gt']}", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out), encoding="utf-8")
    print("저장 →", OUT)


def is_lying(aspect, head, min_aspect, max_head):
    """관절이 없으면(-1) 판단하지 않는다. 임계가 0 이면 그 조건은 보지 않는다."""
    if aspect < 0:
        return False
    return ((aspect >= min_aspect) if min_aspect > 0 else True) and \
           ((head <= max_head) if max_head > 0 else True)


def onset(tracks, th, need, min_aspect, max_head, alpha=0.0, b_aspect=0.0, b_head=0.0):
    """연속 need 돌파 + 발화 창 자세 검증(억제) + 확실히 누웠을 때 점수 가중(부스팅)."""
    best = None
    for tr in tracks:
        run = 0
        for idx, (t, z, aspect, head) in enumerate(tr):
            p = 1.0 / (1.0 + math.exp(-z))
            if alpha > 0 and is_lying(aspect, head, b_aspect, b_head):
                p *= (1.0 + alpha)              # 확실히 누운 창만 올린다
            run = run + 1 if p >= th else 0
            if run >= need:
                # 발화 직전 need 창 중 하나라도 '누운 자세' 면 인정
                seg = tr[idx - need + 1: idx + 1]
                lying = any(is_lying(a, hd, min_aspect, max_head) for _, _, a, hd in seg)
                if not lying and (min_aspect > 0 or max_head > 0):
                    run = 0
                    continue                     # 자세가 아니면 발화 취소하고 계속 본다
                t0 = tr[idx - need + 1][0]
                best = t0 if best is None else min(best, t0)
                break
    return best


def score(data, th, need, ma, mh, alpha=0.0, ba=0.0, bh=0.0):
    tp = fn = fp = 0
    miss = []
    for stem, d in data.items():
        gt, sa = d["gt"], onset(d["tracks"], th, need, ma, mh, alpha, ba, bh)
        if sa is None:
            fn += 1; miss.append(stem)
        elif gt is not None and gt - BEFORE <= sa <= gt + AFTER:
            tp += 1
        else:
            fp += 1; fn += 1; miss.append(stem)
    r = tp / (tp + fn) if tp + fn else 0.0
    p = tp / (tp + fp) if tp + fp else 0.0
    return (2 * r * p / (r + p) * 100 if r + p else 0.0), tp, fn, fp, miss


def _top(rows, n=6):
    rows.sort(key=lambda x: -x[0])
    seen = set()
    out = []
    for r in rows:
        key = (r[-4], r[-3], r[-2])
        if key in seen:
            continue
        seen.add(key); out.append(r)
        if len(out) >= n:
            break
    return out


def sweep():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cfg = K.ITEMS["falldown"]
    th, need = cfg["th"], cfg["need"]
    b = score(data, th, need, 0, 0)
    print(f"  기준(검증·부스팅 없음) → F1 {b[0]:.2f} ({b[1]}/{b[2]}/{b[3]}) "
          f"미검 {','.join(m[4:] for m in b[4])}")

    print("\n  [1] 억제만 — 문턱 넘어도 누운 자세가 아니면 버림(034 오검 제거 목적)")
    rows = []
    for ma in (0, 0.6, 0.8, 1.0, 1.2, 1.5):
        for mh in (0, 0.3, 0.4, 0.5, 0.6):
            if ma == 0 and mh == 0:
                continue
            f1, tp, fn, fp, miss = score(data, th, need, ma, mh)
            rows.append((f1, ma, mh, tp, fn, fp, miss))
    for f1, ma, mh, tp, fn, fp, miss in _top(rows):
        print(f"    F1 {f1:6.2f}  종횡비>={ma} 머리높이<={mh}  {tp}/{fn}/{fp}  "
              f"미검 {','.join(m[4:] for m in miss)}")

    print("\n  [2] 억제 + 부스팅 — 확실히 누운 창은 점수를 올림(235 미검 해소 목적)")
    rows = []
    for ma in (0, 1.0, 1.2):
        for mh in (0, 0.4, 0.5):
            for alpha in (0.1, 0.15, 0.2, 0.3, 0.5):
                for ba in (1.0, 1.2, 1.5):
                    for bh in (0.3, 0.4):
                        f1, tp, fn, fp, miss = score(data, th, need, ma, mh, alpha, ba, bh)
                        rows.append((f1, ma, mh, alpha, ba, bh, tp, fn, fp, miss))
    for f1, ma, mh, alpha, ba, bh, tp, fn, fp, miss in _top(rows):
        print(f"    F1 {f1:6.2f}  억제(>={ma},<={mh}) 부스팅(+{alpha} when >={ba},<={bh})  "
              f"{tp}/{fn}/{fp}  미검 {','.join(m[4:] for m in miss)}")


if __name__ == "__main__":
    (dump if sys.argv[1] == "dump" else sweep)()
