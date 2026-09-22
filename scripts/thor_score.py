# -*- coding: utf-8 -*-
"""학습 서버의 방화 실험 가중치를 Thor 배포 경로로 채점한다.

어디서 도나
    작업 PC 에서 돈다. 서버와 Thor 는 서로 못 붙는다(Thor 는 내부망, 서버는 원격).
    양쪽에 붙을 수 있는 것은 작업 PC 뿐이라 여기서 받아서 보낸다.

왜 Thor 인가
    서버 채점(score_kisa.py)은 규칙을 540가지로 훑어 최고값을 취한다. 채점 10편으로 규칙까지
    고르는 셈이라 낙관적이다. Thor 는 배포가 실제로 쓰는 규칙 하나로만 돈다. 이쪽이 정직한 숫자다.

왜 best 와 last 를 둘 다 재나
    채점셋으로 에폭을 고른 실험은 best.pt 에서만 좋고 last.pt 에서 5.9~12.4점 빠진다.
    둘의 차이가 곧 '체크포인트 선택으로 번 점수' 다. 지금 큐는 val_set 을 안 붙였지만
    습관으로 굳혀 둔다.

무엇을 같이 보나
    10편 F1 만 보면 과거 실험들이 전부 동점으로 끝났다(배수 축·하드네거티브 축 측정 불가).
    그래서 변별력이 있는 세 편(195 · 216 · 272)의 개별 성패를 같이 찍는다.

사용
    python thor_score.py <실험이름> [--which best,last] [--keep]
      --keep  Thor 에 올린 가중치를 지우지 않는다(여러 번 다시 잴 때)
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# 주소·경로는 환경변수로 받는다(코드에 IP·계정을 적지 않는다). 기본값은 ssh 별칭이다.
#   SRV_HOST   학습 서버 ssh 이름            기본 nhn-yolo
#   SRV_ROOT   그 안의 저장소 경로
#   THOR_HOST  Thor ssh 주소(사용자@호스트)
#   THOR_ROOT  Thor 의 배포본 경로
SRV = os.environ.get("SRV_HOST", "nhn-yolo")
SRV_ROOT = os.environ.get("SRV_ROOT", "/NHNHOME/WORKSPACE/26mss002_E3/vms")
THOR = os.environ.get("THOR_HOST", "thor")
THOR_ROOT = os.environ.get("THOR_ROOT", "~/Desktop/Project/Kisa")
KEY3 = ("C00_195_0001", "C00_216_0003", "C00_272_0003")   # 변별력이 있는 세 편


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def srv(sh):
    r = run(["ssh", "-o", "ConnectTimeout=25", SRV, sh])
    return r.stdout.strip()


def thor(sh, timeout=3600):
    r = run(["ssh", "-o", "ConnectTimeout=25", THOR, sh], timeout=timeout)
    return r.stdout + r.stderr


def fetch(exp, which, tmp):
    """서버에서 가중치를 받아 작업 PC 에 둔다. 없으면 None."""
    remote = srv(f"ls {SRV_ROOT}/runs/{exp}/*/weights/{which}.pt 2>/dev/null | head -1")
    if not remote:
        print(f"  {which}.pt 없음")
        return None
    local = tmp / f"{exp}_{which}.pt"
    r = run(["scp", "-o", "ConnectTimeout=25", "-q", f"{SRV}:{remote}", str(local)])
    if r.returncode or not local.is_file():
        print(f"  {which}.pt 받기 실패: {r.stderr.strip()[:120]}")
        return None
    return local


def score_on_thor(local_pt, tag, imgsz):
    """Thor 배포 경로로 한 벌만 채점한다(앙상블 끔). 출력 원문을 돌려준다."""
    name = local_pt.name
    r = run(["scp", "-o", "ConnectTimeout=25", "-q", str(local_pt),
             f"{THOR}:{THOR_ROOT}/weights/exp/{name}"])
    if r.returncode:
        return f"[실패] Thor 로 올리지 못했다: {r.stderr.strip()[:200]}"
    out = f"{THOR_ROOT}/_thor_score/{tag}"
    cmd = (
        f"mkdir -p {out} && docker run --rm --runtime=nvidia --network host "
        f"-e PYTHONDONTWRITEBYTECODE=1 -v {THOR_ROOT}:/kisa -v {THOR_ROOT}/data:/data "
        f"-v {out}:/KISAresult -w /kisa --entrypoint python3 kisa-runtime:1.2 "
        f"tools/kisa_items.py --item fire --videos /data/영상/fire --gt /data/GT/fire "
        f"--out /KISAresult --fire-weights /kisa/weights/exp/{name} --fire-weights2 none "
        f"--fire-imgsz2 {imgsz}"
    )
    return thor(cmd)


def digest(text):
    """채점 출력에서 점수 한 줄과 세 편의 성패를 뽑는다."""
    score = ""
    for m in re.finditer(r"정검 (\d+) 미검 (\d+) 오검 (\d+) → 점수 ([0-9.]+)", text):
        score = "정검 %s 미검 %s 오검 %s → %s" % m.groups()
    three = {}
    for m in re.finditer(r"클립 (C00_\d+_\d+):\s*(\S+)", text):
        if m.group(1) in KEY3:
            three[m.group(1)] = m.group(2)
    return score, three


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exp")
    ap.add_argument("--which", default="best,last")
    ap.add_argument("--imgsz", type=int, default=960, help="학습과 같은 해상도로 둔다")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    lines = ["실험 %s · Thor 배포 경로 채점 (imgsz %d)" % (a.exp, a.imgsz), ""]
    for which in [w.strip() for w in a.which.split(",") if w.strip()]:
        print("== %s.pt" % which, flush=True)
        pt = fetch(a.exp, which, tmp)
        if pt is None:
            lines.append("  %-5s 가중치 없음" % which)
            continue
        raw = score_on_thor(pt, "%s_%s" % (a.exp, which), a.imgsz)
        score, three = digest(raw)
        if not score:
            print(raw[-800:])
            lines.append("  %-5s 채점 실패 (원문은 화면 참고)" % which)
            continue
        three_s = " · ".join("%s %s" % (c[-9:], three.get(c, "?")) for c in KEY3)
        print("  %s" % score)
        print("  %s" % three_s)
        lines.append("  %-5s %s" % (which, score))
        lines.append("        %s" % three_s)
        if not a.keep:
            thor("rm -f %s/weights/exp/%s" % (THOR_ROOT, pt.name), timeout=60)

    text = "\n".join(lines) + "\n"
    out = tmp / "thor_score.txt"
    out.write_text(text, encoding="utf-8")
    # 결과는 서버의 그 실험 폴더에 같이 둔다. 나중에 실험별로 한자리에서 본다.
    run(["ssh", "-o", "ConnectTimeout=25", SRV, "mkdir -p %s/results/%s" % (SRV_ROOT, a.exp)])
    run(["scp", "-o", "ConnectTimeout=25", "-q", str(out),
         "%s:%s/results/%s/thor_score.txt" % (SRV, SRV_ROOT, a.exp)])
    print("\n" + text)
    print("서버 results/%s/thor_score.txt 에 저장" % a.exp)


if __name__ == "__main__":
    sys.exit(main())
