# -*- coding: utf-8 -*-
"""/api/queue 의 '실행 중' 을 폴더 존재가 아니라 실제 프로세스(exp_queue.py _one <queue> <name>)로 판단."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
old = '''        if p == "/api/queue":                    # 실험 러너 상태(결과탭 상단). 실행중=_exp/<name> 존재, 로그=runner.log 끝
            q = {"running": sorted(d.name for d in (G / "_exp").glob("*") if d.is_dir()) if (G / "_exp").is_dir() else [],
                 "log": []}'''
new = '''        if p == "/api/queue":                    # 실험 러너 상태(결과탭 상단). 실행중 = 실제 학습 프로세스(exp_queue.py _one <큐> <이름>), 로그=runner.log 끝
            running = []
            try:
                import subprocess as _sp
                ps = _sp.run(["pgrep", "-af", "exp_queue.py _one"], capture_output=True, text=True, timeout=5).stdout
                for line in ps.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[-1] != "_one" and "pgrep" not in line:
                        running.append(parts[-1])          # 마지막 인자 = 실험 이름
            except Exception:
                pass
            q = {"running": sorted(set(running)), "log": []}'''
assert s.count(old) == 1, "queue 앵커 없음"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
