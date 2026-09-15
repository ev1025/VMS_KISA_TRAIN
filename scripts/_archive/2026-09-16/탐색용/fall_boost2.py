# -*- coding: utf-8 -*-
"""쓰러짐: 동역학 점수 부스팅 스윕.

근거: 미검 235 는 SeqNet 점수가 0.238 로 문턱(0.269)에 못 미치지만,
      같은 구간의 머리 하강속도(HVV)는 3.151 로 전체 상위권이다. 두 신호가 상보적이다.
방식: 창 점수에 그 창 직전 구간의 최대 HVV 를 반영해 올린다.
      p' = p * (1 + alpha * min(HVV, cap))
      문턱은 건드리지 않는다(문턱 하향은 비공개 평가셋에서 오검 폭증 위험).
주의: 0패딩 구간은 속도로 치지 않는다(좌표가 원점으로 튀어 속도가 발산한다).
사용: python fall_boost2.py
"""
import json
import math
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "_kisa_port"))
import kisa_items as K            # noqa: E402

SRC = V / "dumps/fall_kin.json"
BEFORE, AFTER = 2.0, 10.0


def hvv_series(obs):
    """관측 프레임 사이의 정규화 하강속도 [(시각, 속도)]. 끊긴 구간은 뺀다."""
    out = []
    for a, b in zip(obs, obs[1:]):
        dt = b[0] - a[0]
        if dt <= 0 or dt > 0.5:
            continue
        out.append((b[0], (b[1] - a[1]) / dt / max(b[2], 1.0)))
    return out


def onset(tracks, th, need, alpha, back, cap):
    """부스팅 적용 후 연속 돌파 시각. back = 창 직전 몇 초의 속도를 볼지."""
    best = None
    for tr in tracks:
        hv = hvv_series(tr["obs"])
        run = 0
        for i, (t, z) in enumerate(tr["curve"]):
            p = 1.0 / (1.0 + math.exp(-z))
            if alpha > 0:
                m = max((v for ts, v in hv if t - back <= ts <= t), default=0.0)
                p *= (1.0 + alpha * min(max(m, 0.0), cap))
            run = run + 1 if p >= th else 0
            if run >= need:
                t0 = tr["curve"][i - need + 1][0]
                best = t0 if best is None else min(best, t0)
                break
    return best


def score(data, th, need, alpha, back, cap):
    tp = fn = fp = 0
    miss = []
    for stem, d in data.items():
        gt, sa = d["gt"], onset(d["tracks"], th, need, alpha, back, cap)
        if sa is None:
            fn += 1; miss.append(stem)
        elif gt is not None and gt - BEFORE <= sa <= gt + AFTER:
            tp += 1
        else:
            fp += 1; fn += 1; miss.append(stem)
    r = tp / (tp + fn) if tp + fn else 0.0
    p = tp / (tp + fp) if tp + fp else 0.0
    return (2 * r * p / (r + p) * 100 if r + p else 0.0), tp, fn, fp, miss


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    th, need = K.ITEMS["falldown"]["th"], K.ITEMS["falldown"]["need"]
    b = score(data, th, need, 0, 0, 0)
    print(f"  기준(부스팅 없음) → F1 {b[0]:.2f} ({b[1]}/{b[2]}/{b[3]}) "
          f"미검·오검 {','.join(m[4:] for m in b[4])}")
    rows = []
    for alpha in (0.02, 0.03, 0.05, 0.08, 0.10, 0.15):
        for back in (0.5, 1.0, 1.5, 2.0):
            for cap in (2.0, 3.0, 4.0, 6.0):
                f1, tp, fn, fp, miss = score(data, th, need, alpha, back, cap)
                rows.append((f1, alpha, back, cap, tp, fn, fp, miss))
    rows.sort(key=lambda x: (-x[0], x[1]))
    print("  부스팅 적용 상위:")
    seen = set()
    for f1, alpha, back, cap, tp, fn, fp, miss in rows:
        key = (tp, fn, fp)
        if key in seen:
            continue
        seen.add(key)
        print(f"    F1 {f1:6.2f}  alpha={alpha} 직전{back}초 상한{cap}  {tp}/{fn}/{fp}  "
              f"실패 {','.join(m[4:] for m in miss)}")
        if len(seen) >= 6:
            break
    # 최고 조합이 안정적인지: 같은 결과가 나오는 파라미터 범위를 센다
    top = rows[0]
    same = sum(1 for r in rows if (r[4], r[5], r[6]) == (top[4], top[5], top[6]))
    print(f"\n  최고 조합과 같은 성적을 내는 파라미터 조합 수: {same}/{len(rows)} "
          f"(넓을수록 과적합이 아니다)")


if __name__ == "__main__":
    main()
