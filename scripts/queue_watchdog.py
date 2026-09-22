# -*- coding: utf-8 -*-
"""큐 감시(주말 무인 운전). 러너가 죽으면 다시 올리고, 큐가 끝나면 사람 모델 규칙 평가를 순서대로 돌린다.

왜 (2026-09-18)
    주말 2일 동안 학습이 끊기지 않아야 한다. 러너(exp_queue.py run)는 nohup 으로 떠 있지만
    예외·OOM·접속 끊김으로 죽을 수 있다. 러너가 죽으면 그 자식 학습도 같이 죽으므로(PDEATHSIG)
    다시 올리면 러너가 last.pt 에서 이어간다(에폭 단위 손실).
    큐가 다 끝나면 손라벨 모델들에 규칙 평가(scripts/rule_eval.py)를 하나씩 돌려 results/<실험>/rules.txt 를 남긴다.

하지 않는 것
    도는 학습을 건드리지 않는다. 러너가 살아 있으면 아무것도 하지 않는다.
    러너를 다시 올릴 때만 exp_queue 의 시작 절차(고아 워커 정리)가 돈다. 그 외에 프로세스를 죽이지 않는다.

사용
    setsid nohup .venv/bin/python scripts/queue_watchdog.py configs/queue_person_20260917.yaml > logs/queue/watchdog.log 2>&1 &
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

import yaml

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import exp_queue as Q     # noqa: E402  (is_done · running_elsewhere · best_pt 를 그대로 쓴다)
import kisa_paths as KP   # noqa: E402

PY = V / ".venv/bin/python"
LOG = V / "logs/queue/watchdog.log"


def log(msg):
    line = f"[{Q._kst('%m-%d %H:%M')} KST] 감시: {msg}"
    print(line, flush=True)


def ps_args():
    try:
        return subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True, timeout=20).stdout.splitlines()
    except Exception:
        return []


def runner_alive(queue_name):
    return any("exp_queue.py" in ln and " run " in ln and queue_name in ln for ln in ps_args())


def scoring_alive():
    return any("exp_queue.py" in ln and " _score " in ln for ln in ps_args())


def start_runner(queue):
    (V / "logs/queue").mkdir(parents=True, exist_ok=True)
    lf = open(V / "logs/queue" / f"runner_{Path(queue).stem}.log", "a", encoding="utf-8")
    subprocess.Popen([str(PY), str(V / "scripts/exp_queue.py"), "run", queue, "--jobs", "1"],
                     cwd=V, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)


def person_exps(exps):
    """규칙 평가 대상 = 사람 항목이고 채점이 끝났고 rules.txt 가 아직 없는 실험(큐 순서대로)."""
    out = []
    for e in exps:
        if e.get("item") not in ("사람",) + tuple(KP.PERSON_ITEMS):
            continue
        if not (V / "results" / e["name"] / "score.txt").is_file():      # 취소 표식(results/<이름>.txt)만 있는 것은 뺀다
            continue
        if (V / "results" / e["name"] / "rules.txt").is_file():
            continue
        out.append(e["name"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("queue")
    ap.add_argument("--every", type=int, default=300, help="확인 간격(초)")
    a = ap.parse_args()
    qname = Path(a.queue).name
    log(f"시작 · 큐 {a.queue} · {a.every}초마다 확인")
    restarts = 0
    while True:
        try:
            exps = yaml.safe_load(open(a.queue, encoding="utf-8"))["experiments"]
        except Exception as e:
            log(f"큐 파일 읽기 실패(다음에 다시): {e!r}"); time.sleep(a.every); continue
        if runner_alive(qname):
            time.sleep(a.every); continue
        busy = Q.running_elsewhere()
        todo = [e["name"] for e in exps if not Q.is_done(e) and e["name"] not in busy]
        if todo:
            restarts += 1
            log(f"러너가 없는데 남은 실험 {len(todo)}개({', '.join(todo[:3])}{' …' if len(todo) > 3 else ''}) → 러너 다시 올림 ({restarts}번째)")
            start_runner(a.queue)
            time.sleep(max(a.every, 600)); continue
        if scoring_alive():
            log("큐는 끝났고 떼어 둔 채점이 아직 돈다 → 기다림"); time.sleep(a.every); continue
        targets = person_exps(exps)
        if not targets:
            log("큐 끝 · 규칙 평가할 사람 모델 없음(전부 rules.txt 있음) → 종료"); return 0
        log(f"큐 끝 → 규칙 평가 {len(targets)}개 순서대로: {', '.join(targets)}")
        for name in targets:
            log(f"규칙 평가 시작 {name}")
            r = subprocess.run([str(PY), str(V / "scripts/rule_eval.py"), name], cwd=V, capture_output=True, text=True)
            log(f"규칙 평가 끝 {name} rc={r.returncode} {(r.stdout or '').strip().splitlines()[-1:] }")
        log("규칙 평가 전부 끝 → 종료")
        return 0


if __name__ == "__main__":
    sys.exit(main())
