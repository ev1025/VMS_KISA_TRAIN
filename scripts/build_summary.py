# -*- coding: utf-8 -*-
"""실험 결과를 한 장으로 모아 results/SUMMARY.md 를 만든다.

왜 있나 (2026-09-23)
    results/ 는 용량 때문에 깃에서 빼 놓았다(96건, score.txt·덤프·meta). 그래서 다른 장비에서
    클론하면 무엇이 얼마였는지 알 방법이 없었다. 대시보드 결과 탭도 데이터가 없으면 빈다.
    숫자만 추려 한 파일로 남기면 클론만 해도 읽을 수 있다.

    사람이 고쳐 쓰는 문서가 아니다. 실험이 끝날 때마다 다시 돌려 덮어쓴다.

쓰는 법
    python scripts/build_summary.py          results/SUMMARY.md 를 새로 쓴다
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kisa_paths as KP

V = KP.V
RES = V / "results"
OUT = RES / "SUMMARY.md"

# 방화 score.txt 에서 규칙별 점수 줄
RE_RULE = re.compile(r"^\s{2}(\S.*?)\s+→\s+([0-9.]+)\s+\(정검 (\d+) 미검 (\d+) 오검 (\d+)\)")
# 사람 score.txt
RE_PERSON = re.compile(r"^(\S+) (\S+): \[(\w+)\].*?→ 점수 ([0-9.]+)")
# 방화 클립별
RE_CLIP = re.compile(r"^  클립 (C00_\d+_\d+): (\S+)")
KEY3 = ("C00_195_0001", "C00_216_0003", "C00_272_0003")   # 변별력이 있는 세 편


def read_meta(d):
    try:
        return json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def parse(d):
    """한 실험 폴더 → 요약 dict. score.txt 가 없으면 None."""
    f = d / "score.txt"
    if not f.is_file():
        return None
    t = f.read_text(encoding="utf-8", errors="replace")
    m = read_meta(d)
    out = {"name": d.name, "item": m.get("item", "?"), "model": m.get("model", ""),
           "n_train": m.get("n_train"), "ended": (m.get("ended") or "")[:10],
           "base": m.get("base"), "extras": m.get("extras") or [],
           "oversample": m.get("oversample") or {},
           "imgsz": (m.get("train") or {}).get("imgsz"),
           "epochs": (m.get("train") or {}).get("epochs")}

    rules = {}
    for line in t.splitlines():
        r = RE_RULE.match(line)
        if r:
            rules.setdefault(r.group(1).strip(), float(r.group(2)))
        p = RE_PERSON.match(line)
        if p:
            rules["%s %s" % (p.group(1), p.group(2))] = float(p.group(4))
    out["rules"] = rules
    out["best"] = max(rules.values()) if rules else None
    # 배포 규칙(정직한 숫자)
    for k, v in rules.items():
        if k.startswith("배포"):
            out["deploy"] = v
    three = {}
    for line in t.splitlines():
        c = RE_CLIP.match(line)
        if c and c.group(1) in KEY3:
            three[c.group(1)] = c.group(2)
    out["three"] = three
    return out


def main():
    rows = [r for r in (parse(d) for d in sorted(RES.iterdir()) if d.is_dir()) if r]
    fire = sorted([r for r in rows if r["item"] == "방화"], key=lambda r: -(r["best"] or 0))
    person = sorted([r for r in rows if r["item"] != "방화"], key=lambda r: -(r["best"] or 0))

    L = []
    A = L.append
    A("# 실험 결과 요약")
    A("")
    A("`results/` 는 용량 때문에 깃에 올리지 않는다(실험 %d건). 숫자만 여기에 모은다." % len(rows))
    A("클론만 해도 무엇이 얼마였는지 읽을 수 있게 하려는 것이다. 원본은 서버의 `results/<실험>/score.txt` 에 있다.")
    A("")
    A("**손으로 고치지 않는다.** `python scripts/build_summary.py` 로 다시 만든다.")
    A("")
    A("만든 때: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    A("")

    try:
        bl = json.loads((RES / "BASELINE.json").read_text(encoding="utf-8"))
        A("## 지금 기준 점수 (제출 경로 실측)")
        A("")
        A("제출 경로(`_kisa_port/tools/kisa_items.py`)로 실제 영상을 돌려 나온 값이다. 스윕 결과가 아니다.")
        A("")
        A("| 항목 | 점수 | 정검 | 미검 | 오검 | 잰 날 | 구성 |")
        A("|---|---|---|---|---|---|---|")
        for k, v in (bl.get("항목") or {}).items():
            if not isinstance(v, dict):
                continue
            A("| %s | **%s** | %s | %s | %s | %s | %s |" % (
                k, v.get("점수", "-"), v.get("정검", "-"), v.get("미검", "-"), v.get("오검", "-"),
                v.get("측정일", "-"), (v.get("구성") or "-")[:70]))
        A("")
        rep = bl.get("오프라인_재현_상태") or {}
        ok = [k for k, x in rep.items() if isinstance(x, dict) and x.get("맞음")]
        no = [k for k, x in rep.items() if isinstance(x, dict) and not x.get("맞음")]
        if ok or no:
            A("덤프로 같은 점수를 낼 수 있는 항목: %s" % (", ".join(ok) or "없음"))
            if no:
                A("낼 수 없는 항목(그 스윕 결과를 쓰면 안 된다): %s" % ", ".join(no))
            A("")
    except Exception:
        pass

    A("## 방화 (%d건)" % len(fire))
    A("")
    A("`최고` 는 규칙 스윕의 최고점이라 낙관적이다. `배포` 가 실제 제출 경로의 값이다.")
    A("`195·216·272` 는 변별력이 있는 세 편으로, 총점이 같아도 이것이 다르면 다른 모델이다.")
    A("")
    A("| 실험 | 최고 | 배포 | 195 | 216 | 272 | 장수 | 해상도 | 끝난 날 |")
    A("|---|---|---|---|---|---|---|---|---|")
    for r in fire:
        t = r["three"]
        A("| `%s` | **%s** | %s | %s | %s | %s | %s | %s | %s |" % (
            r["name"],
            "%.2f" % r["best"] if r["best"] is not None else "-",
            "%.2f" % r["deploy"] if r.get("deploy") is not None else "-",
            t.get(KEY3[0], "-"), t.get(KEY3[1], "-"), t.get(KEY3[2], "-"),
            "{:,}".format(r["n_train"]) if r["n_train"] else "-",
            r["imgsz"] or "-", r["ended"] or "-"))
    A("")

    if person:
        A("## 사람 검출 (%d건)" % len(person))
        A("")
        A("| 실험 | 최고 | 항목별 | 장수 | 해상도 | 끝난 날 |")
        A("|---|---|---|---|---|---|")
        for r in person:
            detail = " · ".join("%s %.2f" % (k, v) for k, v in sorted(r["rules"].items(), key=lambda x: -x[1])[:4])
            A("| `%s` | **%s** | %s | %s | %s | %s |" % (
                r["name"], "%.2f" % r["best"] if r["best"] is not None else "-",
                detail, "{:,}".format(r["n_train"]) if r["n_train"] else "-",
                r["imgsz"] or "-", r["ended"] or "-"))
        A("")

    A("## 무엇으로 학습했나 (방화 상위 12건)")
    A("")
    A("| 실험 | 베이스 | 더한 것 | 오버샘플 |")
    A("|---|---|---|---|")
    for r in fire[:12]:
        A("| `%s` | %s | %s | %s |" % (
            r["name"], r["base"] or "-",
            ", ".join(r["extras"]) or "-",
            ", ".join("%s×%s" % (k, v) for k, v in r["oversample"].items()) or "-"))
    A("")
    A("`human_fire` 가 오버샘플에 있으면 그 점수는 무효다. 채점 10편 2,520장이 그 안에 들어 있다(2026-09-22 확인).")
    A("")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("%s · 실험 %d건 (방화 %d · 사람 %d)" % (OUT.relative_to(V), len(rows), len(fire), len(person)))


if __name__ == "__main__":
    main()
