# -*- coding: utf-8 -*-
"""영상 검수용 박스 덤프를 미리 만들어 둔다.

왜 (2026-09-16)
    검수 탭에서 모델을 고르면 그때부터 추론을 시작해 방화 한 편에 2분이 걸렸다.
    화면 앞에서 기다릴 일이 아니다. 학습이 끝나면 같이 만들어 두는 것이 맞다.
    앞으로 만들어지는 실험은 scripts/exp_queue.py 가 채점 직후에 만든다(여기는 지난 것 채우기).

무엇을 하나
    (모델 x 클립) 중 아직 없는 것을 하나씩 만든다. 이미 있으면 건너뛴다(중간에 끊겨도 이어서 돈다).
    순서는 쓸모 순이다.
        1) 배포에 쓰는 실험
        2) 채점셋 mAP 높은 순
    갈래를 맞춘다. 불 모델은 방화 10편, 사람 모델은 침입·배회·쓰러짐 70편.

    학습과 같이 돌아가므로 한 번에 하나만 돌린다. GPU 를 막지 않는다.

사용
    .venv/bin/python scripts/boxdump_backfill.py                # 전부(없는 것만)
    .venv/bin/python scripts/boxdump_backfill.py --only <실험명> # 한 실험만
    .venv/bin/python scripts/boxdump_backfill.py --limit 50     # 50개만
    .venv/bin/python scripts/boxdump_backfill.py --plan         # 무엇을 할지만 보여준다
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP           # noqa: E402
from model_rank import rank, DEPLOY   # noqa: E402  실제 KISA 점수 순

PY = V / ".venv/bin/python"
OUT = V / "dumps/fire_box"
PERSON_ITEMS = ("침입", "배회", "쓰러짐")
TOP_DEFAULT = 10                  # 갈래별로 이 개수만 미리 만든다(나머지는 고를 때 그 자리에서)


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


def kind_of(exp):
    import json as _j
    mj = V / "results" / exp / "meta.json"
    try:
        return "fire" if (_j.loads(mj.read_text(encoding="utf-8")) or {}).get("item") == "방화" else "person"
    except Exception:
        return "fire"


def clips_for(kind):
    items = ("방화",) if kind == "fire" else PERSON_ITEMS
    out = []
    for it in items:
        try:
            out += sorted(p.stem for p in KP.videos(it).rglob("*.mp4"))
        except Exception:
            pass
    return sorted(set(out))


def work_list(top=TOP_DEFAULT):
    """갈래별 상위 top 개만. 순서는 model_rank(실제 KISA 점수) 그대로."""
    picked, seen = [], {"fire": 0, "person": 0}
    for exp, kind, key, why in rank():
        if seen[kind] >= top:
            continue
        seen[kind] += 1
        picked.append((exp, kind, why))
    todo = []
    for exp, kind, why in picked:
        for stem in clips_for(kind):
            if (OUT / exp / (stem + ".jsonl")).is_file():
                continue
            todo.append((exp, stem, kind, why))
    return picked, todo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="이 실험만")
    ap.add_argument("--limit", type=int, default=0, help="이 개수만")
    ap.add_argument("--plan", action="store_true", help="무엇을 할지만 보여준다")
    ap.add_argument("--top", type=int, default=TOP_DEFAULT, help="갈래별 상위 몇 개까지 (기본 10)")
    a = ap.parse_args()

    exps, todo = work_list(a.top)
    if a.only:                       # 큐가 채점 직후에 부르는 길. 순위와 무관하게 그 실험만 만든다
        todo = [(a.only, stem, kind_of(a.only), "채점 직후")
                for stem in clips_for(kind_of(a.only))
                if not (OUT / a.only / (stem + ".jsonl")).is_file()]
    if a.limit:
        todo = todo[:a.limit]

    have = sum(len(list(d.glob("*.jsonl"))) for d in OUT.glob("*/"))
    print(f"실험 {len(exps)}개 · 이미 있는 덤프 {have}개 · 만들 것 {len(todo)}개")
    est = sum(120 if t[2] == "fire" else 45 for t in todo)
    print(f"예상 {est // 3600}시간 {est % 3600 // 60}분 (불 120초·사람 45초 기준)\n")
    if a.plan:
        cur = None
        for exp, stem, kind, why in todo:
            if exp != cur:
                n = sum(1 for t in todo if t[0] == exp)
                tag = '  <= ' + DEPLOY[exp] if exp in DEPLOY else ''
                print(f"  {exp:36} {kind:6} {why:22} {n}편{tag}")
                cur = exp
        return 0

    t0 = time.time()
    ok = err = 0
    for i, (exp, stem, kind, why) in enumerate(todo, 1):
        s = time.time()
        r = subprocess.run([str(PY), str(V / "scripts/exp_boxdump.py"), exp, stem],
                           capture_output=True, text=True, cwd=str(V), timeout=3600)
        good = (OUT / exp / (stem + ".jsonl")).is_file()
        ok += good
        err += not good
        left = (len(todo) - i) * (time.time() - t0) / i
        print(f"[{i}/{len(todo)}] {exp} {stem} {'완료' if good else '실패'} "
              f"{time.time() - s:.0f}초 · 남은 예상 {left / 3600:.1f}시간", flush=True)
        if not good:
            print("   " + ((r.stdout or "") + (r.stderr or "")).strip()[-200:], flush=True)
    print(f"\n완료 {ok} · 실패 {err} · {(time.time() - t0) / 3600:.1f}시간")
    return 0


if __name__ == "__main__":
    sys.exit(main())
