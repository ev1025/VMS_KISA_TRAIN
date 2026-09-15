# -*- coding: utf-8 -*-
"""학습프레임 초기화 전 손라벨 파일을 시각 붙은 이름으로 따로 백업(기존 _backup_labels 는 하루 한 번만 남김)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
old = """                with _SAVE_LOCK:
                    _backup_labels(fl)
                    rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                    keep = [r for r in rows if r.get("clip") != clip]"""
new = """                with _SAVE_LOCK:
                    if fl.exists():                       # 초기화 직전 상태를 시각 붙여 따로 남긴다(복구용)
                        bdir = fl.parent / "_backup"; bdir.mkdir(exist_ok=True)
                        shutil.copyfile(fl, bdir / f"{fl.stem}.{time.strftime('%Y%m%d_%H%M%S')}.reset_{clip}.json")
                    rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                    keep = [r for r in rows if r.get("clip") != clip]"""
assert s.count(old) == 1
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
