# -*- coding: utf-8 -*-
"""파생물이 원본보다 낡았는지 전수로 훑는다.

2026-09-16 에 같은 유형을 다섯 번 찾았다. 전부 '만들어 놓고 원본이 바뀐 걸 아무도 안 본' 것이다.
  화면 판정 구현 · 재생바 곡선 · score_kisa 운영규칙 · 학습셋 handset_* · 큐 채점 해상도
audit_stale 의 신선도 검사는 파일 3개만 본다. 여기서는 전부 본다.
"""
import datetime as dt
import hashlib
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

V = Path(__file__).resolve().parents[1]

# 아는 사정이라 경고할 필요가 없는 것. 왜 그런지 같이 적는다.
KNOWN = {
    "s2_s960_20260913": "runs/ 가 2026-09-15 재학습 실패(train_failed, epoch 3)로 덮어써졌다. "
                        "덤프가 옳고 가중치가 낡은 것이다. 쓸 수 있는 원본은 logs/_archive 사본뿐이다.",
}
# 계보를 원본 경로로 추적할 수 없는 가중치. 사본이 몇 벌 있는지로 대신 본다.
NO_ORIGIN = {
    "yolo11x-pose.pt": "ultralytics 배포본. 우리 실험 산출물이 아니다",
    "person_v2.pt":    "학습 데이터셋이 2026-09-11 의사라벨 정리 때 삭제됐다(MODELS.json). 재현 불가",
    "person_v3.pt":    "위와 같다",
    "fall_track.pt":   "SeqNet 가중치. runs/fall_track 에서 나왔다",
    "fire_snowfull.pt": "지금 배포에 안 쓴다",
}


def mt(p):
    return p.stat().st_mtime if p.exists() else 0


def ymd(ts):
    return dt.datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "없음"


def newest(d, pats=("*",)):
    best = 0
    for pat in pats:
        for f in Path(d).rglob(pat):
            if f.is_file():
                best = max(best, f.stat().st_mtime)
    return best


HAND = V / "data/학습데이터/손라벨"


def label_rows(fn, want_eval):
    """손라벨에서 그 학습셋이 실제로 쓰는 행만 센다.
    파일 수정 시각만 보면 안 된다. 오늘(2026-09-16) evalset 이 그것 때문에 헛경보가 났다.
    연구개발 영상만 라벨했는데 파일 시각이 바뀌어 '채점셋 검증셋도 낡았다' 고 잘못 잡았다."""
    f = HAND / fn
    if not f.is_file():
        return 0
    rows = json.loads(f.read_text(encoding="utf-8"))
    EV = "kisa_배포_검증영상"
    return sum(1 for r in rows if (EV in (r.get("src") or "")) == want_eval)


def report():
    """전부 훑어 찍는다."""
    print("=" * 78)
    print("1. 학습셋이 손라벨보다 낡았나")
    print("=" * 78)
    src = {"person": mt(HAND / "person_labels.json"), "fire": mt(HAND / "fire_labels.json")}
    sam = newest(V / "data/학습데이터/자동라벨/sam2", ("*.json",))
    print(f"   손라벨 person {ymd(src['person'])} · fire {ymd(src['fire'])} · SAM전파 {ymd(sam)}")
    print()
    print(f"   {'학습셋':<38}{'빌드':>13}{'담긴 장수':>10}  상태")
    for d in sorted((V / "data/학습데이터").iterdir()):
        if not d.is_dir() or d.name in ("손라벨", "자동라벨"):
            continue
        meta = d / "meta.json"
        if not meta.is_file():
            continue
        try:
            m = json.loads(meta.read_text(encoding="utf-8"))
        except Exception:
            continue
        mode = m.get("mode")
        if mode not in src:
            continue
        built = mt(meta)
        newer = []
        if src[mode] > built:
            newer.append("손라벨")
        if sam > built:
            newer.append("SAM전파")
        n = (m.get("train") or 0) + (m.get("val") or 0)
        # 검증셋은 채점셋 라벨만 쓴다. 연구개발 라벨이 늘어도 내용이 안 바뀌므로 시각만으로 판단하지 않는다.
        if d.name.startswith("evalset_"):
            have = m.get("boxes") or m.get("박스")
            want = label_rows(f"{mode}_labels.json", want_eval=True)
            if have and want and abs(have - want) <= 0:
                newer = []
            note = f"채점셋 라벨 {want}행 / 담긴 박스 {have}"
            print(f"   {d.name:<38}{ymd(built):>13}{str(have or n):>10}  "
                  + (f"<-- {'·'.join(newer)} 가 더 새것 ({note})" if newer else f"최신 ({note})"))
            continue
        print(f"   {d.name:<38}{ymd(built):>13}{n:>10}  "
              + (f"<-- {'·'.join(newer)} 가 더 새것" if newer else "최신"))

    print()
    print("=" * 78)
    print("2. 실험 결과가 가중치보다 낡았나 (채점을 다시 안 한 실험)")
    print("=" * 78)
    bad = 0
    for r in sorted((V / "results").iterdir()):
        sc = r / "score.txt"
        if not sc.is_file():
            continue
        pts = list((V / "runs" / r.name).rglob("best.pt"))
        if not pts:
            continue
        w = max(mt(p) for p in pts)
        if w > mt(sc) + 60:
            print(f"   {r.name:<38}채점 {ymd(mt(sc))} < 가중치 {ymd(w)}")
            bad += 1
    print("   없음" if not bad else f"   {bad}건")

    print()
    print("=" * 78)
    print("3. 덤프가 그 실험 가중치보다 낡았나")
    print("=" * 78)
    TL = V / "dumps/score_tl"
    bad = 0
    for f in sorted(TL.glob("*.json")):
        if f.name.startswith("_"):
            continue
        pts = list((V / "runs" / f.stem).rglob("best.pt"))
        if not pts:
            continue
        w = max(mt(p) for p in pts)
        if w > mt(f) + 60:
            why = KNOWN.get(f.stem)
            tag = "  (아는 사정)" if why else ""
            print(f"   {f.name:<38}덤프 {ymd(mt(f))} < 가중치 {ymd(w)}{tag}")
            if why:
                print(f"      {why}")
            else:
                bad += 1
    print("   없음" if not bad else f"   {bad}건")

    print()
    print("=" * 78)
    print("4. 배포 가중치가 그 실험 원본과 같은가")
    print("=" * 78)
    W = V / "_kisa_port/weights/kisa"
    MODELS = json.loads((V / "results/MODELS.json").read_text(encoding="utf-8")).get("models", {})
    for f in sorted(W.glob("*.pt")):
        info = MODELS.get(f.name, {})
        orig = info.get("원본") or info.get("original")
        if not orig:
            why = NO_ORIGIN.get(f.name)
            # 원본을 못 따라가면 사본이 몇 벌인지로 대신 본다
            cop = [q for q in (V / "model" / f.name, V / "_kisa_port/weights/kisa" / f.name) if q.exists()]
            same = len({hashlib.md5(q.read_bytes()).hexdigest() for q in cop}) <= 1
            note = why or "원본 기록이 없다. MODELS.json 에 적어야 한다"
            print(f"   {f.name:<26}원본추적 불가 · 사본 {len(cop)}벌 {'일치' if same else '!!! 불일치'}")
            print(f"      {note}")
            continue
        o = V / orig if not str(orig).startswith("/") else Path(orig)
        if not o.exists():
            print(f"   {f.name:<26}원본 파일이 없다: {orig}")
            continue
        h1 = hashlib.md5(f.read_bytes()).hexdigest()[:12]
        h2 = hashlib.md5(o.read_bytes()).hexdigest()[:12]
        print(f"   {f.name:<26}{'같음' if h1 == h2 else '!!! 다름'}  {h1} / {h2}")



# ---------------------------------------------------------------- 자가 시험
def selfcheck():
    """검사기가 정말 잡는지 스스로 증명한다.

    2026-09-16 에 이 스크립트가 틀린 답을 냈다. 파일 수정 시각만 보고
    evalset 이 낡았다고 했는데, 다시 빌드해 보니 내용이 똑같았다.
    검사기를 만들어 놓고 '맞는지' 를 안 본 것이 원인이다.

    그래서 두 가지를 본다.
      (1) 일부러 낡게 만든 것을 잡는가   - 못 잡으면 검사기가 쓸모없다
      (2) 멀쩡한 것을 안 잡는가          - 잡으면 헛경보라 아무도 안 본다
    """
    ok = True
    TR = V / "data/학습데이터"

    # (1) 가짜로 낡은 학습셋을 만들어 둔다. 손라벨보다 오래된 시각으로.
    tmp = TR / "_selfcheck_stale"
    try:
        (tmp).mkdir(exist_ok=True)
        (tmp / "meta.json").write_text(json.dumps(
            {"name": "_selfcheck_stale", "mode": "person", "train": 1, "val": 0}), encoding="utf-8")
        old = mt(HAND / "person_labels.json") - 86400
        import os
        os.utime(tmp / "meta.json", (old, old))

        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report()
        out = buf.getvalue()
        line = [l for l in out.splitlines() if "_selfcheck_stale" in l]
        hit = bool(line) and "더 새것" in line[0]
        print(f"  (1) 일부러 낡게 만든 학습셋을 잡는가        {'잡음' if hit else '못 잡음 <-- 검사기 고장'}")
        ok &= hit

        # (2) 방금 빌드한 멀쩡한 것을 안 잡는가
        fresh = [l for l in out.splitlines()
                 if "handset_person_20260916" in l or "evalset_person" in l]
        clean = all("더 새것" not in l for l in fresh) and len(fresh) == 2
        print(f"  (2) 방금 만든 최신 학습셋·검증셋을 안 잡는가  {'안 잡음' if clean else '헛경보 <-- 검사기 고장'}")
        for l in fresh:
            print(f"        {l.strip()}")
        ok &= clean
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("  자가 시험 " + ("통과" if ok else "실패"))
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        sys.exit(selfcheck())
    report()