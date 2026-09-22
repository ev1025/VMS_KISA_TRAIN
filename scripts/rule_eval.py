# -*- coding: utf-8 -*-
"""사람 모델 한 실험의 판정 규칙 평가를 끝까지 한다: 트랙 덤프 → 침입·배회 규칙 훑기 → results/<실험>/rules.txt

왜 (2026-09-18)
    큐가 끝난 뒤 손라벨 모델들에 규칙을 여러 가지 적용해 견고한 평가를 남기라는 요청.
    사람이 스크립트를 하나씩 돌리지 않아도 되게 한 줄로 묶는다. 큐 감시(queue_watchdog.py)가 큐가 끝나면 부른다.

무엇을 남기나 (docs/EXPERIMENTS.md 4.5 · 4.10 을 따른다)
    - 지금 규칙 점수(대표값) · 스윕 최고(상한) · LOOCV · 동점 개수
    - 배포 모델과 같은 규칙을 넣은 표(규칙 하나로 두 모델을 다 살릴 수 있는가)
    - 못 잡는 편 목록
    침입: scripts/intr_rule4.py(들어온 사람만 · 히스테리시스) + intr_rule4_common.py
    배회: scripts/loiter_rule4.py(중복 박스 정리 · crowd) + loiter_sweep.py(상수 1,800조합)

덤프 (제출 경로와 같은 검출 방식을 항목별로 따른다. 2026-09-18 에 배회를 타일 덤프로 분석해 엉뚱한 결론을 냈던 일이 있다)
    침입 = person_redump.py: 3x3 타일 + IoU NMS(부분검출 억제 끔 contain 2.0) + 간이 트래커  (PersonDetector 와 같다)
    배회 = server_tdump.py: 전체 프레임 BoT-SORT, conf 0.20, ultralytics NMS 기본        (BotSortPersons 와 같다)
    둘 다 학습 해상도로. dumps/rules/<실험>_<해상도>/{intrusion,loiter}/ 에 두고, 있으면 건너뛴다.

사용
    python scripts/rule_eval.py <실험명> [--imgsz N] [--force]
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "scripts"))
import kisa_paths as KP   # noqa: E402

PY = V / ".venv/bin/python"
S = V / "scripts"


def kst(fmt="%Y-%m-%d %H:%M"):
    return time.strftime(fmt, time.gmtime(time.time() + 9 * 3600))


def n_videos(item):
    return len(list(KP.videos(item).rglob("*.mp4")))


def ensure_dump(pt, item, out, imgsz, log):
    need = n_videos(item)
    have = len(list(out.glob("*.jsonl")))
    if have >= need and need > 0:
        log.write(f"[{kst()}] 덤프 있음 {out} ({have}편)\n"); return True
    out.mkdir(parents=True, exist_ok=True)
    log.write(f"[{kst()}] 덤프 생성 {item} {need}편 → {out} (imgsz {imgsz}, contain 2.0)\n"); log.flush()
    if item == "침입":      # 타일 경로(제출 도구 PersonDetector 와 같게: 3x3 타일 · IoU NMS · 부분검출 억제 끔)
        cmd = [str(PY), str(S / "person_redump.py"), str(pt), "--item", item, "--out", str(out),
               "--imgsz", str(imgsz), "--contain", "2.0"]
    else:                   # 배회 = 전체 프레임 BoT-SORT(제출 도구 BotSortPersons 와 같게: conf 0.20 · ultralytics NMS 기본)
        cmd = [str(PY), str(S / "server_tdump.py"), "--model", str(pt), "--videos", str(KP.videos(item)),
               "--out", str(out), "--stride", str(KP.SAMPLE_STRIDE_S), "--conf", "0.20", "--imgsz", str(imgsz)]
    log.write(f"[{kst()}] 도구 {Path(cmd[1]).name}\n"); log.flush()
    r = subprocess.run(cmd, cwd=V, stdout=log, stderr=subprocess.STDOUT)
    have = len(list(out.glob("*.jsonl")))
    log.write(f"[{kst()}] 덤프 끝 rc={r.returncode} ({have}/{need}편)\n"); log.flush()
    return have >= need


def section(f, title, cmd):
    f.write(f"\n\n===== {title} =====\n$ {' '.join(Path(c).name if c.startswith(str(V)) else c for c in cmd)}\n")
    f.flush()
    r = subprocess.run(cmd, cwd=V, capture_output=True, text=True)
    f.write(r.stdout)
    if r.returncode != 0:
        f.write(f"\n(실패 rc={r.returncode})\n{(r.stderr or '')[-1500:]}\n")
    f.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp")
    ap.add_argument("--imgsz", type=int, default=None, help="덤프 해상도. 기본 = 실험의 학습 해상도")
    ap.add_argument("--force", action="store_true", help="rules.txt 가 있어도 다시 쓴다")
    a = ap.parse_args()
    rdir = V / "results" / a.exp
    out = rdir / "rules.txt"
    if out.is_file() and not a.force:
        print(f"이미 있음 {out}"); return 0
    meta = json.loads((rdir / "meta.json").read_text(encoding="utf-8"))
    if meta.get("item") not in ("사람",) + tuple(KP.PERSON_ITEMS):
        print(f"사람 모델이 아니다({meta.get('item')}). 건너뜀"); return 0
    pt = meta.get("best_pt")
    if not pt or not Path(pt).is_file():
        print("best_pt 없음"); return 1
    imgsz = a.imgsz or int((meta.get("train") or {}).get("imgsz", KP.DEFAULT_IMGSZ))
    droot = V / "dumps" / "rules" / f"{a.exp}_{imgsz}"
    intr, loit = droot / "intrusion", droot / "loiter"
    (V / "logs/rules").mkdir(parents=True, exist_ok=True)
    with open(V / "logs/rules" / f"rule_eval_{a.exp}.log", "a", encoding="utf-8") as log:
        ok1 = ensure_dump(pt, "침입", intr, imgsz, log)
        ok2 = ensure_dump(pt, "배회", loit, imgsz, log)
    rdir.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# 규칙 평가 {a.exp}  ({kst()} KST)\n모델 {pt}\n해상도 {imgsz}  덤프 {droot}\n")
        f.write("읽는 법: '지금 규칙' 이 대표값. '최고' 는 규칙을 고르면 닿는 상한(같은 30편으로 고른 값이라 낙관 포함).\n"
                "LOOCV 는 한 편 빼고 고른 절차의 점수. 배포 모델 표는 규칙 하나가 두 모델을 다 살리는지 본다.\n"
                "맨 앞 '견고 규칙 탐색' 이 결론이다(배포 점수를 안 깨면서 이 모델 점수를 올리는 규칙). 나머지는 축별 근거다.\n")
        if ok1 and ok2:
            # 결론 먼저: 배포 모델과 이 모델에 '같은 규칙 하나' 를 넣어 둘 다 사는 값을 좌표 하강으로 찾는다
            # 대상 = 손라벨 모델들(이 실험 + 기존 손라벨 덤프). 배포는 의사라벨 모델이라 참고로만 찍는다(2026-09-19 지시).
            hand_i = [f"{a.exp}={intr}"] + [x for x in ("손32.6=dumps/intrusion_p1280hand_1280",
                                                        "손10.8=dumps/intrusion_p1280ov2_1280")
                                            if (V / x.split("=", 1)[1]).is_dir()]
            hand_l = [f"{a.exp}={loit}"] + [x for x in ("손32.6=dumps/loiter_p1280hand_bs1280",
                                                        "손10.8=dumps/loiter_p1280ov2_bs1280")
                                            if (V / x.split("=", 1)[1]).is_dir()]
            section(f, "침입 · 견고 규칙 탐색(손라벨 모델들 공통, 13축 좌표 하강)",
                    [str(PY), str(S / "rule_search.py"), "intrusion", "--dumps", *hand_i,
                     "--ref", "배포=dumps/intrusion_tile_v3"])
            section(f, "배회 · 견고 규칙 탐색(손라벨 모델들 공통, 10축 좌표 하강)",
                    [str(PY), str(S / "rule_search.py"), "loiter", "--dumps", *hand_l,
                     "--ref", "배포=dumps/loiter_botsort_v2"])
            section(f, "미검·오검 원인과 촬영 조건 (침입)",
                    [str(PY), str(S / "fail_report.py"), "intrusion", f"{a.exp}={intr}"])
            section(f, "미검·오검 원인과 촬영 조건 (배회)",
                    [str(PY), str(S / "fail_report.py"), "loiter", f"{a.exp}={loit}"])
        if ok1:
            section(f, "침입 · 들어온 사람만(warm_s) · 히스테리시스(lo)", [str(PY), str(S / "intr_rule4.py"), str(intr)])
            section(f, "침입 · 배포 모델과 같은 규칙 하나", [str(PY), str(S / "intr_rule4_common.py"),
                                                    "배포=dumps/intrusion_tile_v3", f"{a.exp}={intr}"])
        else:
            f.write("\n침입 덤프 미완성 → 생략\n")
        if ok2:
            section(f, "배회 · 끊김·대기·체류·발끝 여유(margin)·delay·crowd", [str(PY), str(S / "loiter_rule4.py"), str(loit)])
            section(f, "배회 · 배포 모델과 같은 규칙 하나", [str(PY), str(S / "loiter_rule4_common.py"),
                                                    "배포=dumps/loiter_botsort_v2", f"{a.exp}={loit}"])
            section(f, "배회 · 상수 1,800조합", [str(PY), str(S / "loiter_sweep.py"), str(loit)])
        else:
            f.write("\n배회 덤프 미완성 → 생략\n")
    print(f"완료 → {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
