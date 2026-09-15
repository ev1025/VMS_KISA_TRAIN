# -*- coding: utf-8 -*-
"""러너: best.pt 가 있어도 last.pt 의 에폭이 목표에 못 미치면(중단된 학습) 채점하지 않고 이어서 학습한다.
(중간 best.pt 를 '완료' 로 오판해 미완성 모델을 채점하고 done 처리하던 것)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/scripts/exp_queue.py"
s = io.open(p, encoding="utf-8").read()
old = '''        pt = best_pt(exp)
        n_train = None
        last_pt = V / "runs" / name / exp["model"] / "weights" / "last.pt"
        if pt is None and last_pt.is_file() and (EXP_DIR / name / "data.yaml").is_file():'''
new = '''        pt = best_pt(exp)
        n_train = None
        last_pt = V / "runs" / name / exp["model"] / "weights" / "last.pt"
        unfinished = False
        if last_pt.is_file() and (EXP_DIR / name / "data.yaml").is_file():
            try:                                          # 마지막 에폭 < 목표 에폭 = 중단된 학습(끝난 학습은 epoch=-1 로 저장됨)
                import torch
                ck = torch.load(str(last_pt), map_location="cpu", weights_only=False)
                ep = int(ck.get("epoch", -1)); tgt = int((ck.get("train_args") or {}).get("epochs", 0))
                unfinished = ep >= 0 and ep + 1 < tgt
                del ck
            except Exception as e:
                log(f"{name} last.pt 확인 실패: {e!r}")
        if unfinished:
            pt = None                                     # 중간 best.pt 로 완료 처리하지 않는다
        if pt is None and last_pt.is_file() and unfinished:'''
assert s.count(old) == 1, "앵커"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
