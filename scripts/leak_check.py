# -*- coding: utf-8 -*-
"""채점셋(kisa_배포_검증영상) 프레임이 학습에 들어갔는지 확인한다. 들어갔으면 그 실험 점수는 무효다.

2026-09-22: 이 파일이 handset_* 만 보고 있어서 human_fire 를 놓쳤다.
human_fire 에는 채점 10편 2,520장이 라벨과 함께 들어 있었고, 방화 실험 15건이 그것을
oversample x5 로 학습했다. 배포 중인 fire_fog.pt(= fresh_48k_wildall_20260909, 94.74)도 그중 하나다.
그래서 두 가지를 바꿨다.
  - 학습데이터 폴더를 전부 본다(이름으로 고르지 않는다)
  - 오염된 셋을 실제로 쓴 실험을 results/*/meta.json 에서 찾아 이름을 댄다
"""
import json
from pathlib import Path

V = Path(__file__).resolve().parents[1]
DS = V / "data/학습데이터"
L = DS / "손라벨"
EVAL_MARK = "kisa_배포_검증영상"
SKIP = {"손라벨", "자동라벨"}         # 라벨 원천. 여기에 채점셋이 있는 것은 정상이다


def eval_stems():
    r"""채점 전용 클립의 파일명(확장자 뺀 것).

    이름 규칙(C00_)으로 가르면 안 된다. 배포 견본 중 사람 모델로 채점하지 않는 항목
    (싸움·유기·마케팅·쓰러짐 45편, KISA_악천후_사람)도 C00_ 으로 시작하는데 학습에 쓴다.
    datasets.yaml 의 use: eval 이 유일한 기준이다(빌더도 같은 기준을 쓴다).
    """
    import yaml
    reg = yaml.safe_load((V / "configs/datasets.yaml").read_text(encoding="utf-8"))
    out = set()
    for cat, cfg in reg.items():
        if (cfg or {}).get("use") != "eval":
            continue
        d = V / "data/원본데이터" / cat
        if d.is_dir():
            out |= {p.stem for p in d.rglob("*.mp4")}
    return out


EVAL_STEMS = eval_stems()


def split(fn):
    rows = json.loads((L / fn).read_text(encoding="utf-8"))
    ev = [r for r in rows if EVAL_MARK in (r.get("src") or "")]
    return rows, ev, [r for r in rows if r not in ev]


for fn, tag in (("fire_labels.json", "방화"), ("person_labels.json", "사람")):
    if not (L / fn).is_file():
        continue
    rows, ev, tr = split(fn)
    print("== %s 손라벨 %,d박스" .replace("%,d", "{:,}").format(len(rows)) % tag
          if False else "== %s 손라벨 %s박스" % (tag, format(len(rows), ",")))
    print("   학습에 쓸 수 있는 것  %s박스 / %s장" % (format(len(tr), ","), format(len({(r.get('clip'), r.get('file')) for r in tr}), ",")))
    print("   채점셋(쓰면 안 됨)    %s박스 / %s장" % (format(len(ev), ","), format(len({(r.get('clip'), r.get('file')) for r in ev}), ",")))
    print()

print("== 학습데이터 폴더 전수 검사 (채점 전용 클립 %d편 기준)" % len(EVAL_STEMS))
dirty = {}
for d in sorted(DS.iterdir()):
    img = d / "images"
    if not d.is_dir() or d.name in SKIP or not img.is_dir():
        continue
    names = [p.stem for p in img.rglob("*") if p.is_file()]
    # 프레임 이름 = <클립>_<번호>[_꼬리]. 앞에서부터 잘라 가며 채점 클립인지 본다.
    bad = [n for n in names if any(n.startswith(e) for e in EVAL_STEMS)]
    if d.name.startswith("evalset_"):
        print("   %-34s%6d장 · 채점 %4d개  (채점 전용이라 정상)" % (d.name, len(names), len(bad)))
        continue
    if bad:
        dirty[d.name] = len(bad)
        print("   %-34s%6d장 · 채점 %4d개  <<< 오염" % (d.name, len(names), len(bad)))
    else:
        print("   %-34s%6d장 · 채점 %4d개  깨끗" % (d.name, len(names), len(bad)))

if not dirty:
    print("\n오염된 학습셋 없음.")
    raise SystemExit(0)

print("\n== 그 셋을 실제로 쓴 실험 (이 점수는 무효다)")
hits = []
for m in sorted((V / "results").glob("*/meta.json")):
    try:
        d = json.loads(m.read_text(encoding="utf-8"))
    except Exception:
        continue
    used = sorted({n for n in dirty
                   if n == d.get("base") or n in (d.get("extras") or [])
                   or n in (d.get("oversample") or {})})
    if used:
        hits.append((d.get("name", m.parent.name), d.get("item", "?"), used))
for name, item, used in hits:
    print("   %-38s %-6s %s" % (name, item, ", ".join(used)))
print("\n오염 학습셋 %d개 · 그것으로 학습한 실험 %d건" % (len(dirty), len(hits)))
raise SystemExit(1)
