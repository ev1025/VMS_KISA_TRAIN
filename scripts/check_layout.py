# -*- coding: utf-8 -*-
"""저장소 배치가 docs/file_path.md 2절과 맞는지 확인한다.

왜 있나
    "결과가 어디 갔는지 모르겠다" 가 반복돼서 규칙을 문서로 적었는데, 문서만 있으면
    어긴 것을 사람이 눈으로 찾아야 한다. 이 스크립트가 대신 찾는다.
    scripts/check_models.py 가 모델 계보를 확인하듯, 이건 파일 자리를 확인한다.

사용
    .venv/bin/python scripts/check_layout.py           # 어긴 것만 출력
    .venv/bin/python scripts/check_layout.py --all     # 통과한 항목도 같이

되돌아오는 값: 어긴 것이 하나라도 있으면 1, 없으면 0.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kisa_paths as KP

V = KP.V

# 루트에 둘 수 있는 파이썬 파일. 러너가 프로세스 이름으로 찾거나 상대경로로 부르는 진입점들이다.
ROOT_PY = {"model.py", "score_kisa.py", "config.py"}
# results/ 바로 아래에 둘 수 있는 파일. 실험 하나에 매이지 않는 가로지르는 기록들이다.
# BASELINE.json 은 4항목 실측의 단일 기준이라 일부러 루트에 둔다(check_repro 가 이것만 읽는다).
RESULTS_FILES = {"MODELS.json", "loocv_results.json", "BASELINE.json"}
# 학습 가중치가 아닌 산출물이 들어가는 runs 폴더(SeqNet 등). best.pt 가 없는 게 정상이다.
RUNS_EXCEPT = {"fall_track", "fall_seq", "_eval", "_archive"}

bad, ok = [], []


def running_jobs():
    """지금 학습 중인 실험 이름. 이제 막 시작한 잡은 아직 가중치를 저장하지 않았으므로
    '가중치 없음' 으로 잡으면 안 된다."""
    import subprocess
    try:
        out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return set()
    names = set()
    for line in out.splitlines():
        if "exp_queue.py" in line and " _one " in line:
            names.add(line.split()[-1])          # ... _one <큐> <실험명>
    return names


def check(cond, label, detail=""):
    (ok if cond else bad).append(f"{label}{(' — ' + detail) if detail and not cond else ''}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="통과한 항목도 출력")
    a = ap.parse_args()

    # 1) 루트에 새 스크립트를 만들지 않았나
    stray = sorted(p.name for p in V.glob("*.py") if p.name not in ROOT_PY)
    check(not stray, "루트 파이썬 파일", f"허용 밖 {len(stray)}개: {', '.join(stray)} → scripts/ 로")

    # 2) results/ 바로 아래 흩어진 파일
    loose = sorted(p.name for p in (V / "results").glob("*") if p.is_file() and p.name not in RESULTS_FILES)
    check(not loose, "results/ 루트 파일", f"{len(loose)}개: {', '.join(loose[:6])} → results/<실험>/ 안으로")

    # 3) 결과 폴더에 기록이 하나라도 있나(score.txt 또는 meta.json)
    empty = sorted(d.name for d in (V / "results").iterdir()
                   if d.is_dir() and not (d / "score.txt").is_file() and not (d / "meta.json").is_file())
    check(not empty, "결과 폴더 기록", f"{len(empty)}개가 비었다: {', '.join(empty[:6])}")

    # 4) runs 폴더에 가중치가 있나 (지금 도는 잡은 아직 저장 전이라 제외)
    rd = V / "runs"
    live = running_jobs()
    now = []
    if rd.is_dir():
        for d in sorted(x for x in rd.iterdir() if x.is_dir()):
            if d.name in RUNS_EXCEPT or d.name in live or list(d.rglob("*.pt")):
                continue
            now.append(d.name)
    check(not now, "runs/ 가중치",
          f"{len(now)}개에 .pt 가 없다(중단된 학습 잔해 → logs/_archive 로): {', '.join(now[:6])}")

    # 4-2) 가중치 깊이가 규약(runs/<실험>/<모델>/weights/best.pt)과 맞나
    #      ultralytics 는 --project 를 줘도 기본 runs/detect 아래에 또 만드는 일이 있다.
    #      2026-09-16 에 runs/detect/runs/p960_hand_20260916/... 이 그렇게 생겼고 위 검사는 못 잡았다.
    # 규약이 runs/<실험>/<모델>/weights/ 로 바뀌기 전(2026-09-15 이전)에 만든 것들.
    # 다시 학습할 일이 없어 그대로 둔다. 새로 생기는 것만 잡으면 된다.
    OLD_LAYOUT = {
        "fire_base_20260908", "fire_fasdd_20260908", "fire_fog1_20260908", "fire_fogsnow_20260908",
        "fire_m_snowmix_20260908", "fire_s960_20260908", "fire_snow2_20260908",
        "fire_snowfull_20260908", "fire_snowmix_20260908_1028",
        "fresh_48k_base_20260909", "fresh_48k_fasdd_20260909", "person_v2", "person_v3",
    }
    deep = []
    if rd.is_dir():
        for pt in rd.rglob("weights/*.pt"):
            rel = pt.relative_to(rd).parts          # (<실험>, <모델>, weights, x.pt)
            if len(rel) == 4 or rel[0] in RUNS_EXCEPT or rel[0] in OLD_LAYOUT:
                continue
            deep.append(str(pt.relative_to(V)))
    check(not deep, "runs/ 가중치 깊이",
          f"{len(deep)}개가 runs/<실험>/<모델>/weights/ 자리가 아니다: {', '.join(deep[:3])}")

    # 5) 큐 로그는 logs/queue/<실험>.log 만
    qd = V / "logs/queue"
    odd = sorted(p.name for p in qd.iterdir() if p.is_file() and p.suffix != ".log") if qd.is_dir() else []
    check(not odd, "logs/queue/ 구성", f"{len(odd)}개가 .log 가 아니다: {', '.join(odd[:6])}")

    # 6) 제출 도구 폴더에 관계없는 것이 쌓이지 않았나(file_path.md 4절).
    #    본시험은 제출 후 수정이 안 되므로 '무엇을 제출했는지' 의 경계가 흐려지면 안 된다.
    port = V / "_kisa_port"
    junk = sorted(p.name for p in port.iterdir()
                  if p.name not in {"tools", "weights", "app", "__pycache__"}) if port.is_dir() else []
    check(not junk, "_kisa_port/ 구성",
          f"제출 도구 밖 {len(junk)}개: {', '.join(junk[:6])} → scripts/_archive 로")

    # 7) 소스 폴더에 로그가 섞였나 (__pycache__ 는 .gitignore 가 전역으로 막으므로 보지 않는다)
    dlogs = sorted(p.name for p in (V / "dash_v2").glob("*.log"))
    check(not dlogs, "dash_v2/ 로그", f"{len(dlogs)}개: {', '.join(dlogs)} → logs/ 로")

    # 8) data/ 아래 허가된 두 폴더만
    extra = sorted(d.name for d in (V / "data").iterdir()
                   if d.is_dir() and d.name not in {"원본데이터", "학습데이터"})
    check(not extra, "data/ 하위 폴더", f"허가 밖 {len(extra)}개: {', '.join(extra)}")

    if a.all:
        for line in ok:
            print(f"  통과  {line}")
    for line in bad:
        print(f"  위반  {line}")
    print(f"\n{len(ok)}개 통과 · {len(bad)}개 위반" + ("" if bad else " (docs/file_path.md 2절과 일치)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
