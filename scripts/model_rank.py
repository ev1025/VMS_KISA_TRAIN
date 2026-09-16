# -*- coding: utf-8 -*-
"""실험을 '우리 기준으로 좋은 순' 으로 줄 세운다.

왜 따로 만드나 (2026-09-16)
    mAP 순은 우리 기준이 아니다. 방화에서 mAP 1위(s2_m640 0.392)와 실제 KISA 점수 순위가 다르고,
    앙상블에 쓰는 s2_s960 은 mAP 11위(0.356)인데 놓치던 눈편을 유일하게 보는 모델이다.
    화면(검수 탭)과 백필 순서는 '실제로 점수를 내는 순' 이어야 한다.

무엇으로 줄 세우나
    방화  덤프(dumps/score_tl/<실험>.json)에 지금 배포 규칙을 걸어 낸 F1.
          덤프가 없으면 mAP 로 대신한다(뒤로 밀린다).
    사람  results/<실험>/score.txt 의 침입·배회 F1 평균. 없으면 mAP.
    배포에 쓰는 실험은 맨 앞에 둔다.

쓰는 법
    from model_rank import rank            # [(실험, 갈래, 점수, 근거)] 좋은 순
    python scripts/model_rank.py           # 표로 출력
"""
import json
import re
import sys
from collections import deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))

DEPLOY = {"fresh_48k_wildall_20260909": "방화 앙상블 1번(fire_fog)",
          "s2_s960_20260913": "방화 앙상블 2번(fire_small)",
          "g_wildpos_20260912": "직전 방화 단일 배포본"}
DELAY = 10.0


def _fire_cfg():
    try:
        import kisa_items as K
        c = K.ITEMS["fire"]
        return c["fire"], c["win"], c["hits"]
    except Exception:
        return 0.40, 20, 3


def fire_f1(exp):
    """그 모델의 덤프에 지금 배포 규칙을 걸어 10편을 채점한다. 덤프가 없으면 None."""
    f = V / "dumps/score_tl" / (exp + ".json")
    if not f.is_file():
        return None
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return None
    if len(d) < 10:
        return None
    fth, win, hits = _fire_cfg()
    tp = ms = fp = 0
    for stem, e in d.items():
        q = deque(maxlen=win)
        on = None
        for t, fire, smoke in e["rows"]:
            q.append((t, fire >= fth))
            if sum(1 for _, x in q if x) >= hits:
                on = next(t0 for t0, x in q if x)
                break
        sa = None if on is None else on + DELAY
        gt = e["gt"]
        if sa is None:
            ms += 1
        elif gt - 2 <= sa <= gt + 10:
            tp += 1
        else:
            ms += 1
            fp += 1
    return round(200.0 * tp / (2 * tp + ms + fp), 2) if tp else 0.0


def person_f1(exp):
    """score.txt 의 침입·배회 F1 평균. 없으면 None."""
    f = V / "results" / exp / "score.txt"
    if not f.is_file():
        return None
    vals = [float(x) for x in re.findall(r"→\s*([0-9.]+)\s*\(정검", f.read_text(encoding="utf-8", errors="replace"))]
    return round(sum(vals) / len(vals), 2) if vals else None


def map50(exp):
    f = V / "results" / exp / "eval_map.json"
    if not f.is_file():
        return 0.0
    try:
        return float((json.loads(f.read_text(encoding="utf-8")) or {}).get("map50") or 0.0)
    except Exception:
        return 0.0


def weights_of(exp):
    mj = V / "results" / exp / "meta.json"
    if mj.is_file():
        try:
            p = (json.loads(mj.read_text(encoding="utf-8")) or {}).get("best_pt")
            if p and Path(p).is_file():
                return Path(p)
        except Exception:
            pass
    for c in sorted((V / "runs" / exp).rglob("best.pt")):
        return c
    return None


def rank():
    """[(실험, 갈래, 정렬키, 근거)] 를 좋은 순으로."""
    out = []
    for mj in sorted((V / "results").glob("*/meta.json")):
        exp = mj.parent.name
        if not weights_of(exp):
            continue
        try:
            d = json.loads(mj.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        kind = "fire" if d.get("item") == "방화" else "person"
        f1 = fire_f1(exp) if kind == "fire" else person_f1(exp)
        if f1 is not None:
            key, why = (1, f1), f"KISA F1 {f1}"
        else:
            key, why = (0, map50(exp)), f"mAP {map50(exp):.3f} (F1 없음)"
        out.append((exp, kind, key, why))
    # 배포본 먼저, 그 다음 F1 있는 것(높은 순), 마지막에 F1 없는 것(mAP 순)
    out.sort(key=lambda r: (0 if r[0] in DEPLOY else 1, -r[2][0], -r[2][1]))
    return out


if __name__ == "__main__":
    rows = rank()
    print(f"{'실험':36}{'갈래':7}근거")
    for exp, kind, key, why in rows:
        tag = "  <= " + DEPLOY[exp] if exp in DEPLOY else ""
        print(f"{exp:36}{kind:7}{why}{tag}")
