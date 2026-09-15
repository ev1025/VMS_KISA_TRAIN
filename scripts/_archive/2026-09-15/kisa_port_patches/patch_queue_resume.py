# -*- coding: utf-8 -*-
"""실험 큐 러너: (1) runs/<name>/<model>/weights/last.pt 가 있으면 처음부터가 아니라 이어서 학습(에폭 유지), 이때도 캐시 설정 적용
(2) RAM 캐시 상한을 큐 yaml 에서 올린다(이 서버 RAM 2.2TB; 60k 가드는 다른 환경 기준)."""
import io
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms/"
p = V + "scripts/exp_queue.py"
s = io.open(p, encoding="utf-8").read()
assert "resume_train.py" not in s
old = '''        pt = best_pt(exp)
        n_train = None
        if pt is None:
            d, n_train = build_lists(exp, defaults)
            log(f"{name} 학습 시작 ({exp['model']}, {n_train}장, +{exp.get('extras', [])}, extra={exp.get('extra', {})})")
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / f"{name}.log", "a", encoding="utf-8") as lf:
                rc = subprocess.run(train_cmd(exp, defaults, d / "data.yaml", n_train), cwd=V, stdout=lf, stderr=subprocess.STDOUT,
                                    env=dict(os.environ, CUDA_VISIBLE_DEVICES="0")).returncode'''
new = '''        pt = best_pt(exp)
        n_train = None
        last_pt = V / "runs" / name / exp["model"] / "weights" / "last.pt"
        if pt is None and last_pt.is_file() and (EXP_DIR / name / "data.yaml").is_file():
            # 중단된 학습 → last.pt 에서 이어간다(에폭 유지). 캐시/워커는 큐 설정을 따른다
            a_ = dict(defaults.get("train", {}), **exp.get("train", {}))
            cache = a_.get("cache", "ram")
            n_lines = sum(1 for _ in open(EXP_DIR / name / "train.txt", encoding="utf-8")) if (EXP_DIR / name / "train.txt").is_file() else 0
            if cache == "ram" and n_lines > int(defaults.get("ram_cache_max", 60000)):
                cache = False
            log(f"{name} 이어서 학습(last.pt, {n_lines}장, cache={cache}, workers={a_.get('workers', 8)})")
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / f"{name}.log", "a", encoding="utf-8") as lf:
                rc = subprocess.run([str(PY), str(V / "scripts/resume_train.py"), str(last_pt), "--cache", str(cache), "--workers", str(a_.get("workers", 8))],
                                    cwd=V, stdout=lf, stderr=subprocess.STDOUT, env=dict(os.environ, CUDA_VISIBLE_DEVICES="0")).returncode
            pt = best_pt(exp)
            if rc != 0 or pt is None:
                log(f"{name} 이어서 학습 실패 rc={rc}{' (SIGKILL: OOM 의심 → 캐시/동시잡 확인)' if rc == -9 else ''} (logs/queue/{name}.log)")
                write_meta(exp, defaults, n_lines, pt, started, "train_failed"); return
        elif pt is None:
            d, n_train = build_lists(exp, defaults)
            log(f"{name} 학습 시작 ({exp['model']}, {n_train}장, +{exp.get('extras', [])}, extra={exp.get('extra', {})})")
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR / f"{name}.log", "a", encoding="utf-8") as lf:
                rc = subprocess.run(train_cmd(exp, defaults, d / "data.yaml", n_train), cwd=V, stdout=lf, stderr=subprocess.STDOUT,
                                    env=dict(os.environ, CUDA_VISIBLE_DEVICES="0")).returncode'''
assert s.count(old) == 1, "run_one 앵커"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("exp_queue.py: resume 지원")

q = V + "configs/queue_fire_20260909.yaml"
y = io.open(q, encoding="utf-8").read()
old = "  vram_gate_mib: 100000\n"
new = "  vram_gate_mib: 100000\n  ram_cache_max: 300000        # 이 서버 RAM 2.2TB. 20만장 × 약 0.7MB ≈ 150GB/잡. 60k 가드는 다른 환경 기준\n"
assert y.count(old) == 1
y = y.replace(old, new, 1)
io.open(q, "w", encoding="utf-8").write(y)
print("queue yaml: ram_cache_max 300000")
