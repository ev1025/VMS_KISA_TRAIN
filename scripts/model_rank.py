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
    tx = f.read_text(encoding="utf-8", errors="replace")
    # 형식이 두 가지다(2026-09-16 에 바뀜). 둘 다 읽는다.
    #   옛  : intrusion → 69.23 (정검 18 ...)
    #   지금: 침입 배포해상도 960: [intrusion] 정검 25 ... → 점수 89.29 (90 미달)
    vals = [float(x) for x in re.findall(r"→\s*([0-9.]+)\s*\(정검", tx)]
    if not vals:
        # 지금 형식. 해상도가 둘이면 배포 해상도 줄만 쓴다(실제로 나가는 값이라).
        dep = re.findall(r"배포해상도.*→\s*점수\s*([0-9.]+)", tx)
        vals = [float(x) for x in dep] or [float(x) for x in re.findall(r"→\s*점수\s*([0-9.]+)", tx)]
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


def deployed():
    """배포 중인 가중치(model/*.pt). 실험이 아니라 results/ 에 없어서 따로 읽는다.
    갈래·점수는 results/MODELS.json 하나만 본다(가중치 계보 단일 기준)."""
    out = []
    mj = V / "results/MODELS.json"
    if not mj.is_file():
        return out
    try:
        models = (json.loads(mj.read_text(encoding="utf-8")) or {}).get("models") or {}
    except Exception:
        return out
    for fn, d in models.items():
        pt = V / "model" / fn
        if not pt.is_file():
            continue
        task = str(d.get("task") or "")
        if "person" in task:
            kind = "person"
        elif "fire" in task:
            kind = "fire"
        else:
            continue                       # 자세·SeqNet 은 박스 오버레이 대상이 아니다
        f1s = [v for v in (d.get("kisa_f1") or {}).values() if isinstance(v, (int, float))]
        used = ",".join(d.get("used_by") or []) or "배포"
        if f1s:
            key, why = (1, round(sum(f1s) / len(f1s), 2)), "배포(%s) KISA F1 %.2f" % (used, sum(f1s) / len(f1s))
        else:
            key, why = (0, 0.0), "배포(%s) 점수 기록 없음" % used
        out.append(("deploy:" + fn, kind, key, why))
    return out


def rank():
    """[(실험, 갈래, 정렬키, 근거)] 를 좋은 순으로."""
    out = deployed()
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
    # F1 내림차순만 본다(2026-09-18). 배포본을 맨 앞에 고정하던 것을 뺐다.
    # 고정하면 목록이 점수 순으로 보이는데 실제로는 아니라서 오해를 부른다.
    #   (예전 순서: 1위 94.74 · 2위 88.89 · 3위 84.21 · 4위 88.89 <- 3위가 4위보다 낮았다)
    # 배포본은 순서 대신 이름표(DEPLOY)로 알아본다.
    # 정렬키 r[2] = (F1 있으면 1 없으면 0, 점수). F1 있는 것이 먼저, 그 안에서 높은 순.
    out.sort(key=lambda r: (-r[2][0], -r[2][1]))
    return out


if __name__ == "__main__":
    rows = rank()
    print(f"{'실험':36}{'갈래':7}근거")
    for exp, kind, key, why in rows:
        tag = "  <= " + DEPLOY[exp] if exp in DEPLOY else ""
        print(f"{exp:36}{kind:7}{why}{tag}")
