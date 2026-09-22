# -*- coding: utf-8 -*-
"""학습을 띄운 뒤 GPU 를 실제로 얼마나 쓰는지 재서, 모자라면 batch 를 키워 이어서 다시 돌린다.

왜 (2026-09-18)
    batch 는 사람이 미리 정하는데, 데이터·해상도·병렬 여부에 따라 실제 사용량이 크게 달라진다.
    실제로 GPU 절반(92GB/183GB)만 쓰며 몇 시간 돈 적이 있고, 반대로 너무 키워 OOM 도 났다.
    띄운 뒤 재서 고치는 편이 미리 맞히는 것보다 확실하다.

어떻게
    1. exp_queue.py _one 으로 도는 학습을 찾는다.
    2. 학습이 자리를 잡을 때까지 기다린다(WARM 초).
    3. GPU 사용량을 여러 번 재서 안정된 값을 얻는다.
    4. 남는 자리가 SLACK 보다 크면 batch 를 목표치에 맞춰 키운다.
       yaml 을 고치고, 그 잡을 끊고, 같은 이름으로 다시 띄운다.
       러너의 _one 은 last.pt 가 있으면 resume_train 으로 이어가므로 에포크를 안 잃는다.
    5. 실험 하나당 최대 MAX_FIX 번만 고친다(무한 반복 방지).

주의
    OOM 이 나면 학습이 죽는다. 그래서 목표를 전체의 TARGET(기본 90%)까지만 잡고,
    한 번에 1.6배를 넘겨 키우지 않는다.

사용
    python scripts/gpu_autofit.py <큐yaml> [--target 0.90] [--slack-gb 30] [--warm 420]
"""
import argparse
import io
import re
import subprocess
import sys
import time
from pathlib import Path

V = Path(__file__).resolve().parents[1]
PY = V / ".venv/bin/python"

ap = argparse.ArgumentParser()
ap.add_argument("queue")
ap.add_argument("--target", type=float, default=0.90, help="GPU 를 이만큼까지 쓴다(0~1)")
ap.add_argument("--slack-gb", type=float, default=30.0, help="이보다 많이 남으면 고친다")
ap.add_argument("--warm", type=int, default=420, help="띄운 뒤 재기까지 기다리는 초")
ap.add_argument("--max-fix", type=int, default=2, help="실험 하나당 고치는 횟수 상한")
ap.add_argument("--dry", action="store_true", help="재보기만 하고 고치지 않는다(한 번 돌고 끝)")
a = ap.parse_args()
QUEUE = V / a.queue
LOG = V / "logs/queue/gpu_autofit.log"
LOG.parent.mkdir(parents=True, exist_ok=True)


def log(m):
    s = "[%s] %s" % (time.strftime("%m-%d %H:%M"), m)
    print(s, flush=True)
    with io.open(LOG, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def gpu():
    """(사용 MiB, 전체 MiB). 못 읽으면 (0, 0)."""
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                            "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10).stdout
        u, t = [int(x.strip()) for x in o.strip().splitlines()[0].split(",")]
        return u, t
    except Exception:
        return 0, 0


def running_one():
    """[(pid, 실험이름)] — exp_queue.py _one 으로 도는 학습. 같은 실험은 하나로 묶는다."""
    seen = {}
    try:
        o = subprocess.run(["pgrep", "-af", "exp_queue.py"], capture_output=True, text=True, timeout=10).stdout
        for ln in o.splitlines():
            w = ln.split()
            for i, x in enumerate(w):
                if x.endswith("exp_queue.py") and i + 3 < len(w) and w[i + 1] == "_one":
                    seen.setdefault(w[i + 3], int(w[0]))   # 래퍼와 본체가 둘 다 잡힌다. 하나만 둔다
                    break
    except Exception:
        pass
    return [(p, n) for n, p in seen.items()]


def batch_of(name):
    """yaml 에서 그 실험의 batch. (값, 줄번호)"""
    txt = io.open(QUEUE, encoding="utf-8").read().splitlines()
    hit = None
    for i, ln in enumerate(txt):
        if re.search(r"name:\s*%s\b" % re.escape(name), ln):
            hit = i
        if hit is not None and i >= hit and "batch:" in ln:
            m = re.search(r"batch:\s*(\d+)", ln)
            if m:
                return int(m.group(1)), i
    return None, None


def set_batch(line_no, new):
    txt = io.open(QUEUE, encoding="utf-8").read().splitlines(True)
    txt[line_no] = re.sub(r"batch:\s*\d+", "batch: %d" % new, txt[line_no])
    io.open(QUEUE, "w", encoding="utf-8").write("".join(txt))


def epochs_done(name):
    for p in sorted((V / "runs" / name).rglob("results.csv")):
        try:
            return len(io.open(p, encoding="utf-8").read().strip().splitlines()) - 1
        except Exception:
            return 0
    return 0


log("시작 · 큐 %s · 목표 %.0f%% · 여유 기준 %.0fGB · 예열 %d초%s"
    % (a.queue, a.target * 100, a.slack_gb, a.warm, " · 재보기만" if a.dry else ""))

if a.dry:                                              # 한 번 재서 무엇을 할지만 적고 끝낸다
    used, tot = gpu()
    print("GPU 사용 %.0fGB / %.0fGB · 남음 %.0fGB" % (used / 1024, tot / 1024, (tot - used) / 1024))
    js = running_one()
    print("도는 학습:", js or "없음")
    if len(js) > 1:
        print("주의: 잡이 %d개다. GPU 사용량은 그 합이라 한 잡의 몫을 알 수 없다." % len(js))
        print("      실제 동작에서는 잡이 하나가 될 때까지 기다렸다가 고친다(아래 값은 참고용).")
    for _pid, nm in js:
        b_, ln_ = batch_of(nm)
        if not b_:
            print("  %-30s yaml 에 batch 없음" % nm); continue
        would = int(b_ * min(1.6, (tot * a.target) / max(1, used)))
        act = "그대로" if (tot - used) / 1024.0 <= a.slack_gb or would <= b_ else ("batch %d -> %d" % (b_, would))
        print("  %-30s batch %-4d 에포크 %-3d 판단: %s" % (nm, b_, epochs_done(nm), act))
    raise SystemExit(0)
fixed = {}
seen_since = {}

while True:
    jobs = running_one()
    if not jobs:
        time.sleep(60); continue
    if len(jobs) > 1:
        # GPU 사용량은 모든 잡의 합이라, 잡이 여럿이면 한 잡의 몫을 알 수 없다.
        # 그 상태에서 batch 를 키우면 OOM 이 난다. 하나가 될 때까지 기다린다.
        time.sleep(120); continue
    now = time.time()
    for pid, name in jobs:
        seen_since.setdefault(name, now)
        if now - seen_since[name] < a.warm:
            continue                                   # 아직 자리를 안 잡았다
        if fixed.get(name, 0) >= a.max_fix:
            continue
        cur, tot = gpu()
        if not tot:
            continue
        # 여러 번 재서 흔들림을 거른다(검증 단계에는 일시적으로 낮게 나온다)
        vals = [cur]
        for _ in range(4):
            time.sleep(20); vals.append(gpu()[0])
        used = max(vals)                               # 최고점을 쓴다(OOM 은 최고점에서 난다)
        free_gb = (tot - used) / 1024.0
        if free_gb <= a.slack_gb:
            log("%s · 사용 %.0fGB/%.0fGB · 남음 %.0fGB — 충분히 쓰고 있다"
                % (name, used / 1024, tot / 1024, free_gb))
            fixed[name] = a.max_fix                    # 더 안 본다
            continue
        b, ln = batch_of(name)
        if not b:
            log("%s · yaml 에서 batch 를 못 찾았다. 건너뛴다" % name); continue
        target_mib = tot * a.target
        new = int(b * min(1.6, target_mib / max(1, used)))   # 한 번에 1.6배까지만
        if new <= b:
            fixed[name] = a.max_fix; continue
        ep = epochs_done(name)
        log("%s · 사용 %.0fGB/%.0fGB · 남음 %.0fGB · %d에포크 완료 → batch %d→%d 로 올려 이어서 돌린다"
            % (name, used / 1024, tot / 1024, free_gb, ep, b, new))
        set_batch(ln, new)
        subprocess.run(["kill", str(pid)])
        time.sleep(20)
        subprocess.run(["pkill", "-f", "model.py train.*%s" % name])
        time.sleep(20)
        subprocess.Popen(["setsid", str(PY), "-u", str(V / "scripts/exp_queue.py"),
                          "_one", str(QUEUE), name],
                         cwd=str(V),
                         stdout=io.open(V / ("logs/queue/%s_runner.log" % name), "a"),
                         stderr=subprocess.STDOUT)
        fixed[name] = fixed.get(name, 0) + 1
        seen_since[name] = time.time()                 # 다시 예열 시간을 준다
        log("%s · 다시 띄웠다(이어서). 고친 횟수 %d/%d" % (name, fixed[name], a.max_fix))
    time.sleep(60)
