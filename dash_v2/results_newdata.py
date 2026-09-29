# -*- coding: utf-8 -*-
"""결과 탭 데이터(2026-09-29 재설계). 새 데이터 실험만, 비교 블록으로 보인다.

블록 = 대조군 하나 + 독립변수 하나만 다른 실험들. 사람이 정하는 것만 configs/result_blocks.yaml 에 적는다
(질문 · 독립변수 · 대조군 · 실험별 조건 · 결론). 나머지는 파일에서 읽고 손으로 옮겨 적지 않는다.
  대상 실험 · 작업 PC 채점: scripts/review_cache.py 의 eligible() · _current() · official()
  학습 인자: runs/<실험>/<모델>/args.yaml(학습 전이면 큐 yaml 항목) · 돈 에폭: results.csv 줄 수
  optimizer: logs/queue/<실험>.log 의 'MuSGD(lr=0.01, momentum=0.9)' 꼴(ultralytics auto 가 반복 수로 고른다)
  검증셋(best 선택용): _exp/<실험>/data.yaml 의 val 파일(사진 이름 목록 해시로 같음을 가린다)
블록마다 통제변수(모든 실험이 같은 설정)와 독립변수를 여기서 가르고, vary 밖 설정이 다르면 교란 변수로 내보낸다.
학습 진행 · 예상 종료는 화면이 /api/queue 를 같이 읽어 합친다.
확인: .venv/bin/python dash_v2/results_newdata.py (판정 계산 자가 점검 + 블록 요약 출력)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

G = Path(__file__).resolve().parent.parent
if str(G / "scripts") not in sys.path:
    sys.path.insert(0, str(G / "scripts"))
import review_cache as RC  # noqa: E402

BLOCKS = G / "configs/result_blocks.yaml"
ITEMS = {"사람": ["intrusion", "loitering"], "방화": ["fire"]}
SKIP = {"name", "project", "data", "save_dir", "exist_ok", "resume", "workers", "cache", "device",
        "plots", "verbose", "save", "save_period", "time"}           # 실험 이름 · 경로 · 저장 · 로더(결과와 무관)
SHOW = ["model", "imgsz", "batch", "epochs", "patience", "seed", "multi_scale", "optimizer"]   # 통제변수 · 학습 설정에 따로 보이는 인자
LABEL = {"model": "모델", "imgsz": "해상도", "batch": "배치", "epochs": "Epoch", "patience": "Patience", "seed": "Seed",
         "multi_scale": "Multi_scale", "optimizer": "Optimizer", "data": "학습 데이터", "val": "검증셋"}
RE_OPT = re.compile(r"\b([A-Za-z]+)\(lr=([0-9.e-]+)(?:, momentum=([0-9.]+))?\)")
_OPT = {}                                                          # 찾은 optimizer 는 안 바뀐다


def _entries():
    out = {}
    for q in sorted((G / "configs").glob("queue*.yaml")):
        try:
            d = yaml.safe_load(q.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for e in d.get("experiments") or []:
            if e.get("name"):
                out[e["name"]] = e
    return out


def _item(c):
    return "방화" if c.get("item") == "방화" else "사람"


def _info(exp):
    """results/<실험>/run_info.json: 학습 서버에서 한 번 적어 두는 학습 인자 · 검증셋 · 돈 에폭 요약.
    runs/ · _exp/ · logs/ 가 없는 사본(서버 B)은 이것을 읽는다(2026-09-29)."""
    f = G / "results" / exp / "run_info.json"
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except Exception:
        return None


def _args(exp, e):
    """(학습 인자, 큐에 적힌 값뿐인가). model 은 시작 가중치 이름만(yolo11s = COCO 사전학습)."""
    fs = sorted((G / "runs" / exp).glob("*/args.yaml"))
    info = _info(exp)
    if not fs and info:
        return dict(info["args"]), False
    if fs:
        d = yaml.safe_load(fs[0].read_text(encoding="utf-8")) or {}
        planned = False
    else:
        d = dict(e.get("train") or {}, **(e.get("extra") or {}), model=e.get("model") or "")
        planned = True
    d["model"] = Path(str(d.get("model") or "")).name.replace(".pt", "")
    d = {k: v for k, v in d.items() if k not in SKIP}
    if exp not in _OPT:
        f = G / "logs/queue" / f"{exp}.log"
        if f.is_file():
            with f.open(encoding="utf-8", errors="ignore") as fh:
                for i, ln in enumerate(fh):
                    m = RE_OPT.search(ln)
                    if m or i > 5000:
                        if m:
                            _OPT[exp] = m.group(0)
                        break
    if exp in _OPT:
        d["optimizer"] = _OPT[exp]                                 # args.yaml 의 'auto' 대신 실제로 고른 것
    return d, planned


def _val(exp, e):
    """{"key": 같음을 가를 값, "text": 읽는 말, "note": 짧은 부연}. val_small 은 실험마다 자기 학습 목록에서 뽑는 같은 규칙이라 규칙으로 묶는다."""
    v = None
    try:
        v = Path((yaml.safe_load((G / "_exp" / exp / "data.yaml").read_text(encoding="utf-8")) or {}).get("val") or "")
    except Exception:
        pass
    if (v is None or not v.is_file()) and (_info(exp) or {}).get("val"):
        return _info(exp)["val"]
    if (v is None or not v.is_file()) and e.get("val_set"):
        v = G / e["val_set"]
    if v is None or not v.is_file():
        return {"key": None, "text": "학습 시작 시 러너가 결정", "note": "미정"}
    if v.name == "val_small.txt":
        return {"key": "val_small", "text": "학습 목록 무작위 600장", "note": "학습과 겹침"}
    names = sorted(Path(x).name for x in v.read_text(encoding="utf-8").splitlines()
                   if x.strip() and not x.endswith("/000.jpg"))      # 000.jpg = 러너가 넣는 캐시 분리용 빈 사진
    return {"key": hashlib.md5("\n".join(names).encode()).hexdigest()[:10],
            "text": f"자체 CCTV {len(names):,}장", "note": "미학습 클립"}


def _data(c):
    return [c.get("base")] + list(c.get("extras") or []) + [f"{k} ×{v}" for k, v in (c.get("oversample") or {}).items()]


def lo_ck(sc, it):
    """best · last 중 F1 낮은 쪽(같으면 last). 에폭 운을 실력으로 안 읽으려고 낮은 쪽으로 비교한다."""
    s = sc.get(it) or {}
    b, l = s.get("best"), s.get("last")
    if not (b and l):
        return "best" if b else ("last" if l else None)
    return "best" if b["f1"] < l["f1"] else "last"


def run(exp, E):
    e = E.get(exp) or {}
    try:
        meta = json.loads((G / "results" / exp / "meta.json").read_text(encoding="utf-8")) or {}
    except Exception:
        meta = {}
    c = meta or e
    item = _item(c)
    args, planned = _args(exp, e)
    sc = {}
    for ck, per in RC.official(exp).items():
        for it, o in per.items():
            if it in ITEMS[item]:
                sc.setdefault(it, {})[ck] = {"tp": o["정검"], "fn": o["미검"], "fp": o["오검"], "f1": o["점수"],
                                             "res": o["res"], "bad": o["bad"]}
    csv = sorted((G / "runs" / exp).glob("*/results.csv"))
    ep = max(0, len(csv[0].read_text().splitlines()) - 1) if csv else (_info(exp) or {}).get("epochs_run")
    n = meta.get("n_train")
    if not n and (G / "_exp" / exp / "train.txt").is_file():
        with (G / "_exp" / exp / "train.txt").open() as fh:
            n = sum(1 for _ in fh) - 1                                 # 첫 줄은 캐시 분리용 빈 사진
    if meta.get("status") == "trained":
        st = "done" if all(ck in sc.get(it, {}) for it in ITEMS[item] for ck in RC.CKPTS) else "scoring"
    elif meta:
        st = meta.get("status") or "?"
    elif ep is not None:
        st = "train"
    elif (G / "results" / exp / "score.txt").is_file():
        st = "skip"                                                    # 러너가 건너뜀 · 취소 표시로 둔 것
    else:
        st = "queue"
    val = _val(exp, e)
    if meta.get("status") == "trained" and not planned and csv and val["key"] and not (G / "results" / exp / "run_info.json").is_file():
        ri = {"args": args, "val": val, "epochs_run": ep}                  # 학습 서버에서 한 번 적어 둔다(사본은 이것을 읽는다)
        (G / "results" / exp / "run_info.json").write_text(json.dumps(ri, ensure_ascii=False), encoding="utf-8")
    return {"exp": exp, "item": item, "items": ITEMS[item], "status": st, "new": bool(c) and RC._current(dict(c, item=item)),
            "data": _data(c), "n_train": n, "args": args, "planned": planned, "epochs_run": ep, "val": val,
            "ended": meta.get("ended"), "scores": sc, "lo": {it: lo_ck(sc, it) for it in ITEMS[item]}}


def verdict(r, c):
    """대조군 대비: 항목마다 낮은 쪽 체크포인트의 정검 수 차이. 합이 2편 미만이면 동률."""
    if r["status"] != "done" or c["status"] != "done":
        return None
    d = {it: r["scores"][it][r["lo"][it]]["tp"] - c["scores"][it][c["lo"][it]]["tp"] for it in r["items"]}
    t = sum(d.values())
    return {"delta": d, "total": t, "call": "동률" if abs(t) < 2 else ("개선" if t > 0 else "하락")}


def _same(vals):
    return len({json.dumps(v, sort_keys=True, ensure_ascii=False) for v in vals}) == 1


def block(b, R):
    ids = [b["control"]] + [x for x in b["runs"] if x != b["control"]]
    rs = [R[x] for x in ids]
    vary = set(b.get("vary") or [])
    same, diffs = [], []
    for k in sorted(set.intersection(*(set(r["args"]) for r in rs))):   # 모든 판에 있는 인자만(대기 판은 큐에 적힌 값뿐)
        if _same([r["args"][k] for r in rs]):
            same.append(k)
        else:
            diffs.append({"key": k, "values": {r["exp"]: r["args"][k] for r in rs}})
    known = [r["val"]["key"] for r in rs if r["val"]["key"]]
    if not _same(known or [0]):
        diffs.append({"key": "val", "values": {r["exp"]: r["val"]["text"] for r in rs}})
    common = [x for x in rs[0]["data"] if all(x in r["data"] for r in rs)]
    if not _same([sorted(r["data"]) for r in rs]):
        diffs.append({"key": "data", "values": {r["exp"]: [x for x in r["data"] if x not in common] for r in rs}})
    fin = all(r["status"] in ("done", "scoring") for r in rs)
    for d in diffs:
        d["label"] = LABEL.get(d["key"], d["key"])
        d["declared"] = d["key"] in vary
        if d["key"] == "patience" and fin and all(r["epochs_run"] == r["args"].get("epochs") for r in rs):
            d["harmless"] = "모든 실험 계획 에폭 완주, 조기 종료 없음"
    val_known = rs[0]["val"]["key"] and _same(known) and len(known) == len(rs)
    return {**{k: b.get(k) for k in ("id", "date", "title", "question", "iv", "rule_extra", "same_data", "conclusion", "note")},
            "control": ids[0], "members": ids[1:], "labels": b["runs"], "item": rs[0]["item"],
            "same": {"train": [[k, rs[0]["args"][k]] for k in SHOW if k in same],
                     "rest": len([k for k in same if k not in SHOW]),
                     "data": common, "data_all": "data" not in {d["key"] for d in diffs},
                     "val": rs[0]["val"] if val_known else None},
            "diffs": diffs, "planned": any(r["planned"] for r in rs),
            "verdicts": {x: verdict(R[x], R[ids[0]]) for x in ids[1:]}}


def build():
    if not (G / "results").is_dir():                                 # 결과 사본이 없는 서버
        return {"error": "이 서버에는 학습 결과(results)가 없습니다. 결과 탭은 학습 서버(서버 A)에서 보세요"}
    cfg = yaml.safe_load(BLOCKS.read_text(encoding="utf-8")) or {}
    E = _entries()
    names = []
    for b in cfg.get("blocks") or []:
        for x in [b["control"], *b["runs"]]:
            if x not in names:
                names.append(x)
    others = [x for x, _m in RC.eligible() if x not in names]         # 블록 밖 새 데이터 판: 끝난 것
    for f in sorted((G / "runs").glob("*/*/results.csv")):            # + 도는 것
        x, e = f.parent.parent.name, E.get(f.parent.parent.name)
        if x in names or x in others or (G / "results" / x / "meta.json").is_file() or (G / "results" / x / "score.txt").is_file():
            continue
        if e and str(e.get("model") or "").startswith("yolo") and RC._current(dict(e, item=_item(e))):
            others.append(x)
    R = {x: run(x, E) for x in names + others}
    return {**{k: v for k, v in cfg.items() if k != "blocks"},          # dv · key_clips · terms(용어 풀이) 등은 그대로 넘긴다
            "blocks": [block(b, R) for b in cfg.get("blocks") or []], "others": others, "runs": R}


if __name__ == "__main__":
    t = {"best": {"tp": 26, "f1": 92.86}, "last": {"tp": 28, "f1": 94.92}}
    assert lo_ck({"intrusion": t}, "intrusion") == "best"
    assert lo_ck({"intrusion": {"best": {"f1": 90.0}, "last": {"f1": 90.0}}}, "intrusion") == "last"
    a = {"status": "done", "items": ["fire"], "lo": {"fire": "last"}, "scores": {"fire": {"last": {"tp": 7}}}}
    c = dict(a, scores={"fire": {"last": {"tp": 6}}})
    assert verdict(a, c)["call"] == "동률" and verdict(dict(a, scores={"fire": {"last": {"tp": 8}}}), c)["call"] == "개선"
    D = build()
    for b in D["blocks"]:
        print(b["title"], "| 대조군", b["control"], "| 통제 학습 설정", b["same"]["train"], "외", b["same"]["rest"], "| 검증셋", b["same"]["val"])
        for d in b["diffs"]:
            print("   ", "독립변수" if d["declared"] else ("차이(영향 없음)" if d.get("harmless") else "교란 변수"), d["label"], d["values"])
        for x, v in b["verdicts"].items():
            print("   ", x, D["runs"][x]["status"], v and (v["call"], v["delta"]))
    print("블록에 없는 실험:", D["others"])
