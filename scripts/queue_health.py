# -*- coding: utf-8 -*-
"""큐가 이상하게 돌고 있지 않은지 한 번에 본다.

2026-09-17 에 세 가지가 한꺼번에 났다.
  러너가 두 개 떠서 같은 실험을 동시에 띄움
  _one 을 잘못 죽여 학습이 고아가 됨(끝나도 채점이 안 됨)
  러너가 죽어 대기 실험이 영영 안 돎
그때마다 눈으로 ps 를 뒤졌다.

주의: 에폭 사이 검증(mAP) 구간에는 학습 워커가 잠깐 사라진다. 죽은 것이 아니다.
      로그가 최근에 쓰였으면 살아 있는 것으로 본다.
"""
import collections
import subprocess
import sys
import time
from pathlib import Path

import yaml

V = Path(__file__).resolve().parents[1]
QUEUE = sys.argv[1] if len(sys.argv) > 1 else "configs/queue_res1280_20260915.yaml"
QUIET_S = 300          # 로그가 이만큼 조용하면 죽은 것으로 본다

out = subprocess.run(["ps", "-eo", "pid,ppid,etime,args"],
                     capture_output=True, text=True, timeout=20).stdout.splitlines()

runners, ones = [], {}
trains = collections.defaultdict(list)
for ln in out:
    w = ln.split()
    if len(w) < 4:
        continue
    pid, ppid, et = w[0], w[1], w[2]
    args = " ".join(w[3:])
    # 그 러너가 '이 큐' 를 보는지까지 확인한다.
    # 큐 이름을 안 보면 남의 큐를 보는 러너를 내 것으로 세어 "정상" 이라고 한다(2026-09-17).
    if ("exp_queue.py" in args and " run " in args and "/bin/bash" not in args
            and Path(QUEUE).name in args):
        runners.append((pid, et))
    for i, x in enumerate(w):
        if x.endswith("exp_queue.py") and i + 3 < len(w) and w[i + 1] == "_one":
            ones[w[i + 3]] = (pid, et)
    if "model.py" in args and " train " in args and "/_exp/" in args:
        trains[args.split("/_exp/", 1)[1].split("/", 1)[0]].append((pid, ppid))

q = yaml.safe_load((V / QUEUE).read_text(encoding="utf-8"))
exps = [e["name"] for e in q["experiments"]]
done = {n for n in exps if (V / "results" / n / "score.txt").is_file()}
bad = 0

print(f"큐 {QUEUE}   실험 {len(exps)}개 · 완료 {len(done)}개")
print()
print("1. 러너")
if not runners:
    left = set(exps) - done
    if left:
        print(f"   없음  <-- 대기 {len(left)}개가 영영 안 돈다"); bad += 1
    else:
        print("   없음 (남은 실험도 없다)")
elif len(runners) > 1:
    print(f"   {len(runners)}개  <-- 같은 실험을 동시에 띄울 수 있다"); bad += 1
    for pid, et in runners:
        print(f"      pid {pid}  {et}")
else:
    print(f"   1개 (pid {runners[0][0]}, {runners[0][1]})  정상")

print()
print("2. 도는 학습")
if not trains:
    print("   없음")
for name, procs in sorted(trains.items()):
    roots = [p for p, pp in procs if pp == "1"]
    if name in ones:
        state = f"부모 _one pid {ones[name][0]} ({ones[name][1]})"
    elif roots:
        state = "고아  <-- 끝나도 채점이 안 된다"; bad += 1
    else:
        state = "러너 밖에서 띄운 것"
    dup = "  <-- 두 벌 이상!" if len(roots) > 1 else ""
    if dup:
        bad += 1
    print(f"   {name:<30}{len(procs):>3}프로세스  {state}{dup}")

print()
print("3. _one 은 있는데 학습 프로세스가 없는 것")
zombie = []
for n in ones:
    if n in trains:
        continue
    lg = V / "logs/queue" / (n + ".log")
    quiet = time.time() - lg.stat().st_mtime if lg.is_file() else 1e9
    if quiet < QUIET_S:
        print(f"   {n}  검증 중으로 보임(로그가 {quiet:.0f}초 전에 쓰임)")
    else:
        zombie.append((n, quiet))
if not zombie and not any(n not in trains for n in ones):
    print("   없음")
for n, qs in zombie:
    print(f"   {n}  <-- 로그가 {qs/60:.0f}분째 조용하다. 죽었을 수 있다"); bad += 1

print()
print("4. 대기 중인데 아무 데도 없는 실험")
waiting = [n for n in exps if n not in done and n not in trains and n not in ones]
if not waiting:
    print("   없음")
for n in waiting:
    print(f"   {n}" + ("" if runners else "  <-- 러너가 없어 영영 안 돈다"))

print()
print("정상" if not bad else f"문제 {bad}건")
sys.exit(0 if not bad else 1)
