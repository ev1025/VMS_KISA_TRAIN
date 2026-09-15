# -*- coding: utf-8 -*-
"""영상 검수에서 고를 만한 모델의 예측 박스를 미리 만들어 둔다.

왜 필요한가
    검수 화면에서 모델을 고르면 그 자리에서 추론을 시작한다(exp_boxdump.py).
    클립 하나에 수백 프레임이라 몇 십 초씩 기다려야 하고, 다른 모델로 바꿀 때마다 반복된다.
    자주 보는 조합을 미리 만들어 두면 고르는 즉시 뜬다.

무엇을 만드나
    갈래(불·사람)별로 채점셋 mAP50 상위 N개 모델 x 그 항목에서 채점한 클립들.
    이미 있는 덤프는 건너뛴다. 중간에 끊어도 다시 돌리면 남은 것만 이어서 만든다.

사용
    python scripts/prebuild_boxdump.py                  # 갈래별 상위 3개
    python scripts/prebuild_boxdump.py --top 5
    python scripts/prebuild_boxdump.py --kind person    # 사람 모델만
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exp_boxdump as EB

V = EB.V
CLIP_RE = re.compile(r"클립\s+(\S+?):")


def dump_exists(exp, stem):
    """exp_boxdump.py 가 쓰는 자리와 같은 경로. 있으면 건너뛴다."""
    return (V / "dumps/fire_box" / exp / (stem + ".jsonl")).is_file()


def experiments():
    """가중치가 남아 있는 실험들. (갈래, mAP50, 실험명, 항목)"""
    out = []
    for mj in sorted((V / "results").glob("*/meta.json")):
        try:
            m = json.loads(mj.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        pt = m.get("best_pt")
        if not pt or not Path(pt).is_file():
            continue
        item = m.get("item") or "방화"
        kind = "fire" if item == "방화" else "person"
        ej = mj.parent / "eval_map.json"
        map50 = None
        if ej.is_file():
            try:
                map50 = (json.loads(ej.read_text(encoding="utf-8")) or {}).get("map50")
            except Exception:
                pass
        out.append((kind, map50, mj.parent.name, item))
    return out


def clips_of(exp):
    """그 실험의 score.txt 에 적힌 채점 클립들. 검수에서 실제로 열어 보는 것들이다."""
    st = V / "results" / exp / "score.txt"
    if not st.is_file():
        return []
    seen = []
    for ln in st.read_text(encoding="utf-8", errors="replace").splitlines():
        m = CLIP_RE.search(ln)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3, help="갈래별로 위에서 몇 개 모델까지")
    ap.add_argument("--kind", default="all", choices=["all", "fire", "person"])
    a = ap.parse_args()

    exps = experiments()
    picked = []
    for kind in (["fire", "person"] if a.kind == "all" else [a.kind]):
        same = [e for e in exps if e[0] == kind]
        same.sort(key=lambda e: (e[1] is None, -(e[1] or 0)))     # mAP 높은 순, 없는 건 뒤로
        picked += same[: a.top]

    if not picked:
        print("만들 대상이 없습니다."); return 1

    # 어떤 클립을 만들지. mAP 만 낸 실험은 score.txt 에 클립 줄이 없으므로
    # 같은 갈래의 다른 실험(채점까지 한 것)에서 클립 목록을 모아 빌려 쓴다.
    fallback = {}
    for kind, _, exp, _item in exps:
        for c in clips_of(exp):
            fallback.setdefault(kind, [])
            if c not in fallback[kind]:
                fallback[kind].append(c)

    todo = []
    for kind, map50, exp, item in picked:
        cl = clips_of(exp) or fallback.get(kind, [])
        for stem in cl:
            if not dump_exists(exp, stem):
                todo.append((exp, stem, kind, item, map50))

    print(f"대상 모델 {len(picked)}개 · 만들 덤프 {len(todo)}개")
    for kind, map50, exp, item in picked:
        n = sum(1 for t in todo if t[0] == exp)
        print(f"  {kind:6s} {exp:34s} item={item} mAP={map50} · 남은 {n}개")
    if not todo:
        print("전부 이미 있습니다."); return 0

    ok = err = 0
    t0 = time.time()
    for i, (exp, stem, kind, _item, _m) in enumerate(todo, 1):
        try:
            rc = EB.dump(exp, stem)
        except Exception as e:
            rc = 1
            print(f"  [{i}/{len(todo)}] 예외 {exp} {stem}: {e!r}")
        if rc == 0:
            ok += 1
        else:
            err += 1
        el = time.time() - t0
        print(f"  [{i}/{len(todo)}] {exp} {stem} rc={rc} · 경과 {el/60:.1f}분 "
              f"· 남은 예상 {(el / i) * (len(todo) - i) / 60:.1f}분", flush=True)

    print(f"완료 {ok}개 · 실패 {err}개 · 총 {(time.time()-t0)/60:.1f}분")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
