# -*- coding: utf-8 -*-
"""손라벨 미세조정 모델(person_hand_20260910)의 침입·배회 F1 을 잰다.

러너의 score_person 과 같은 경로(kisa_items.py)로 돌려야 94.74 와 비교가 된다.
결과는 results/<실험>/score.txt 로 남겨 대시보드 결과 탭에 뜨게 한다.
학습 imgsz 가 1280 이므로 추론도 1280 으로 맞춘다(EXPERIMENTS.md §1-A).
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "scripts")
import kisa_paths as KP  # noqa: E402

V = KP.V
PY = V / ".venv/bin/python"
KI = V / "_kisa_port/tools/kisa_items.py"
EXP = "person_hand_20260910"
PT = V / "runs" / EXP / "yolo11s/weights/best.pt"
IMGSZ = 1280
RES = V / "results" / EXP

assert PT.is_file(), PT
out = [f"=== {EXP} 사람 항목 ===", f"# 모델 {PT} · 추론 imgsz {IMGSZ}"]
for item in KP.PERSON_ITEMS:
    kitem = KP.kisa_item(item)
    vids = KP.videos(item)
    print(f"[{item}] 채점 시작 ({kitem})", flush=True)
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run([str(PY), str(KI), "--item", kitem,
                            "--videos", str(vids), "--gt", str(vids), "--maps", str(KP.ZONE_MAPS),
                            "--out", str(Path(td) / "sa"), "--person-weights", str(PT),
                            "--person-imgsz", str(IMGSZ)],
                           capture_output=True, text=True, cwd=V, timeout=14400)
    hits = [l.strip() for l in (r.stdout or "").splitlines() if l.strip().startswith(f"[{kitem}]")]
    clips = [l.rstrip() for l in (r.stdout or "").splitlines() if l.strip().startswith("클립 ")]
    if hits:
        # score.txt 규격: "<규칙> → <F1> (정검 n 미검 n 오검 n)"
        import re
        m = re.search(r"정검 (\d+) 미검 (\d+) 오검 (\d+) → 점수 ([\d.]+)", hits[-1])
        if m:
            out.append(f"  {kitem} → {m.group(4)}  (정검 {m.group(1)} 미검 {m.group(2)} 오검 {m.group(3)})")
        print("  " + hits[-1], flush=True)
    else:
        out.append(f"  {kitem} → 채점 실패")
        print("  실패:", (r.stderr or "")[-300:], flush=True)
    if clips:
        out.append(f"=== 클립별 ({kitem}) ===")
        out += ["  " + c.strip() for c in clips]

RES.mkdir(parents=True, exist_ok=True)
(RES / "score.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print("저장 →", RES / "score.txt", flush=True)
