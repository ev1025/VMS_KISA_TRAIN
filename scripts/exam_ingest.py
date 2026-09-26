# -*- coding: utf-8 -*-
"""시험 PC 전체 리허설(/test) 결과를 받아 채점하고 기준값과 편별로 대조한다 (2026-09-26).

시험 PC 콘솔이 /test 가 끝나면 항목 폴더의 SA 를 zip 으로 묶어 ssh 표준입력으로 넘긴다.
    .venv/bin/python scripts/exam_ingest.py --run <run> -            zip 을 표준입력으로. stdout = JSON 한 덩어리(ASCII)
    .venv/bin/python scripts/exam_ingest.py --run <run> <zip경로>    손으로 넣을 때
    .venv/bin/python scripts/exam_ingest.py --selfcheck

결과 (results/exam_pc_<run>/, 대시보드 결과 탭이 실험처럼 읽는다)
    upload.zip   받은 그대로
    <항목>/*.xml SA
    meta.json    zip 의 meta + item "사람"(결과 탭이 줄마다 항목별로 펼친다)
    score.txt    첫 줄들 = 결과 탭 형식 "fire → 90.00 (정검 9 미검 1 오검 1)", 그 아래 기준값과 다른 편
    score.json   f1 · counts · n_diff · n_flip · text
기준값 = results/_exam_ref/<항목>/*.xml (작업 PC 가 배포본으로 파일 80편을 돌린 SA). 없으면 대조를 건너뛴다.
채점은 판정기(_kisa_port/tools/kisa_items.py)의 read_alarms · score 를 그대로 쓴다. 이 스크립트는 xml 만 읽는다.
ssh 로 돌면 cwd 가 홈이다 → 경로는 전부 이 파일 기준 절대경로.
"""
import argparse
import io
import json
import re
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "_kisa_port/tools"))
sys.path.insert(0, str(ROOT / "scripts"))
from kisa_items import read_alarms, score, BEFORE_S, AFTER_S   # noqa: E402  판정기와 같은 채점
import kisa_paths as KP                                          # noqa: E402

ITEMS = ("쓰러짐", "방화", "침입", "배회")                        # 시험 PC 결과 폴더의 하위 폴더 이름 = 표시 순서
RE_RUN = re.compile(r"[A-Za-z0-9_.-]+")
RE_MEMBER = re.compile(r"(쓰러짐|방화|침입|배회)/([^/\\]+\.xml)")


def log(msg):
    print(msg, file=sys.stderr, flush=True)                      # stdout 은 JSON 한 덩어리만


def clip_rows(sa_dir, gt_dir):
    """편별 (정답 첫 경보, SA 첫 경보, 판정) + 채점 쌍. 정답 xml 이 있는 편 전부를 본다(없는 SA 는 미검).
    판정 규칙은 시험 PC 콘솔 score_dir 과 같다."""
    rows, pairs = {}, []
    for g in sorted(gt_dir.glob("*.xml")):
        sa = sa_dir / g.name
        gts, sas = read_alarms(g), (read_alarms(sa) if sa.is_file() else [])
        pairs.append((gts, sas))
        gt0 = gts[0]["start_s"] if gts else None
        sa0 = sas[0]["start_s"] if sas else None
        v = ("정검" if gt0 is not None and sa0 is not None and gt0 - BEFORE_S <= sa0 <= gt0 + AFTER_S
             else "미검" if sa0 is None else "오검")
        rows[g.stem] = {"gt": gt0, "sa": sa0, "verdict": v}
    return rows, score(pairs)


def fmt(v):
    return "None" if v is None else ("%g" % v)


def ingest(run, data, gt_root=None, ref_root=None, results_root=None):
    """zip(bytes) → 채점·대조 결과 dict. 파일은 results/exam_pc_<run>/ 에 쓴다."""
    if not RE_RUN.fullmatch(run or ""):
        raise SystemExit("run 이름이 잘못됐습니다: %r" % run)
    results = Path(results_root) if results_root else KP.V / "results"
    ref = Path(ref_root) if ref_root else results / "_exam_ref"
    rd = results / ("exam_pc_" + run)                             # 반드시 results/ 바로 아래 한 단계(결과 탭이 읽는 깊이)
    if rd.exists():
        shutil.rmtree(rd)                                         # 같은 run 이 다시 오면 다시 채점(멱등)
    rd.mkdir(parents=True)
    (rd / "upload.zip").write_bytes(data)                         # 죽어도 원본은 남는다

    meta, n = {}, 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name == "meta.json":
                try:
                    meta = json.loads(z.read(name).decode("utf-8"))
                except ValueError:
                    meta = {}
                continue
            m = RE_MEMBER.fullmatch(name)
            if not m:
                continue                                          # 다른 항목 · .. · 절대경로는 건너뜀
            dst = rd / m.group(1) / m.group(2)
            dst.parent.mkdir(exist_ok=True)
            dst.write_bytes(z.read(name))
            n += 1
    log("받음 %s: SA %d개" % (rd.name, n))

    head, body, f1, counts = [], [], {}, {}
    n_diff = n_flip = 0
    for it in ITEMS:
        sa_dir = rd / it
        if not sa_dir.is_dir():
            continue                                              # 건너뛴 항목
        gt_dir = (Path(gt_root) / KP.ITEM_DIR[it][0]) if gt_root else KP.videos(it)
        rows, s = clip_rows(sa_dir, gt_dir)
        f1[it] = s["점수"]
        counts[it] = {"정상검출": s["정상검출"], "미검출": s["미검출"], "오검출": s["오검출"]}
        head.append("%s → %.2f (정검 %d 미검 %d 오검 %d)" % (KP.kisa_item(it), s["점수"], s["정상검출"], s["미검출"], s["오검출"]))
        line = "[%s] 시험PC 정 %d 미 %d 오 %d  F1 %.2f" % (it, s["정상검출"], s["미검출"], s["오검출"], s["점수"])
        if not (ref / it).is_dir():
            body += ["", line + "   |   기준 없음"]
            continue
        rrows, rs = clip_rows(ref / it, gt_dir)
        body += ["", line + "   |   기준 정 %d 미 %d 오 %d  F1 %.2f" % (rs["정상검출"], rs["미검출"], rs["오검출"], rs["점수"])]
        for clip in sorted(rows):
            x, y = rows[clip], rrows.get(clip, {"sa": None, "verdict": "미검"})
            if x["sa"] == y["sa"] and x["verdict"] == y["verdict"]:
                continue
            n_diff += 1
            flip = x["verdict"] != y["verdict"]
            n_flip += flip
            d = "" if x["sa"] is None or y["sa"] is None else " (차 %+.1fs)" % (x["sa"] - y["sa"])
            body.append("  %s %s  gt=%s  시험PC sa=%s %s  |  기준 sa=%s %s%s" % (
                "★" if flip else " ", clip, fmt(x["gt"]), fmt(x["sa"]), x["verdict"], fmt(y["sa"]), y["verdict"], d))
    body += ["", "다른 편 %d개 (★ = 판정이 뒤집힌 편)" % n_diff]
    # 결과 탭 파서는 '이름 → 점수 (정검 …)' 줄을 읽는다. '클립 X:' 로 시작하는 줄은 클립 판정으로 읽으니 쓰지 않는다
    text = "\n".join(head) + "\n" + "\n".join(body) + "\n"
    (rd / "score.txt").write_text(text, encoding="utf-8")

    # item "사람" = 결과 탭이 score.txt 의 줄 이름(fire/intrusion/…)을 보고 항목별 행으로 펼친다
    meta.update({"item": "사람", "name": rd.name, "ingested_at": datetime.now().isoformat(timespec="seconds")})
    (rd / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    out = {"run": run, "f1": f1, "counts": counts, "n_diff": n_diff, "n_flip": n_flip, "files": n, "text": text}
    (rd / "score.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def selfcheck():
    """네트워크·실데이터 없이: 정답 2편(쓰러짐 1 · 방화 1), SA 는 정검 1 · 오검 1, 기준은 둘 다 정검."""
    t = Path(tempfile.mkdtemp())
    gx = lambda st, d: ("<K><Library><Clip><Alarms><Alarm><StartTime>%s</StartTime><AlarmDescription>%s</AlarmDescription>"
                        "</Alarm></Alarms></Clip></Library></K>" % (st, d))
    for it, clip, gt, sa, ref, desc in [("쓰러짐", "C00_003_0003", "00:03:18", "00:03:20", "00:03:19", "Falldown"),
                                        ("방화", "C00_272_0003", "00:02:03", "00:02:33", "00:02:04", "Fire")]:
        g = t / "gt" / KP.ITEM_DIR[it][0]; g.mkdir(parents=True)
        (g / (clip + ".xml")).write_text(gx(gt, desc), encoding="utf-8")
        r = t / "res" / "_exam_ref" / it; r.mkdir(parents=True)
        (r / (clip + ".xml")).write_text(gx(ref, desc), encoding="utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("쓰러짐/C00_003_0003.xml", gx("00:03:20", "Falldown"))
        z.writestr("방화/C00_272_0003.xml", gx("00:02:33", "Fire"))
        z.writestr("../evil.xml", "x"); z.writestr("기타/a.xml", "x")
        z.writestr("meta.json", json.dumps({"run": "t", "pc": "시험PC"}, ensure_ascii=False))
    out = ingest("20260926_000000_selfcheck", buf.getvalue(), gt_root=t / "gt", results_root=t / "res")
    rd = t / "res" / "exam_pc_20260926_000000_selfcheck"
    assert out["f1"] == {"쓰러짐": 100.0, "방화": 0.0}, out["f1"]
    assert out["n_diff"] == 2 and out["n_flip"] == 1, (out["n_diff"], out["n_flip"])   # 쓰러짐 1초 차 · 방화 뒤집힘
    assert out["files"] == 2 and not (t / "evil.xml").exists() and not (rd / "기타").exists(), "다른 경로는 안 푼다"
    first = (rd / "score.txt").read_text(encoding="utf-8").splitlines()[0]
    assert re.match(r"^\s*(.+?)\s+→\s+([0-9.]+)\s+\(정검 (\d+) 미검 (\d+) 오검 (\d+)\)", first) and first.startswith("falldown → 100.00"), first
    assert not any(l.lstrip().startswith("클립") for l in out["text"].splitlines()), "결과 탭이 클립 판정으로 읽는 줄은 안 쓴다"
    meta = json.loads((rd / "meta.json").read_text(encoding="utf-8"))
    assert meta["item"] == "사람" and meta["pc"] == "시험PC" and (rd / "upload.zip").is_file()
    again = ingest("20260926_000000_selfcheck", buf.getvalue(), gt_root=t / "gt", results_root=t / "res")
    assert again["f1"] == out["f1"], "같은 run 을 다시 받아도 같다"
    json.loads(json.dumps(out, ensure_ascii=True))
    try:
        ingest("../x", b"")
        raise AssertionError("run 이름 검사")
    except SystemExit:
        pass
    shutil.rmtree(t)
    print("exam_ingest 자체 점검 통과")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("src", nargs="?", help="zip 경로. '-' 면 표준입력")
    ap.add_argument("--run")
    ap.add_argument("--gt-root", help="(점검용) 정답 xml 뿌리 덮어쓰기")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args(argv)
    if a.selfcheck:
        return selfcheck()
    if not a.run or not a.src:
        ap.error("--run 과 zip(또는 -)이 필요합니다")
    data = sys.stdin.buffer.read() if a.src == "-" else Path(a.src).read_bytes()
    out = ingest(a.run, data, gt_root=a.gt_root)
    print(json.dumps(out, ensure_ascii=True), flush=True)          # ASCII 만 → 받는 쪽 인코딩 사고 차단
    log("채점 끝: " + " · ".join("%s %.2f" % kv for kv in out["f1"].items()) + " · 다른 편 %d (뒤집힘 %d)" % (out["n_diff"], out["n_flip"]))


if __name__ == "__main__":
    sys.exit(main())
