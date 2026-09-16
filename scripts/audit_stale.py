# -*- coding: utf-8 -*-
"""최신화되지 않은 코드를 찾는다.

계기(2026-09-16)
    침입 재현이 9점 어긋난 원인은 "같은 판정을 여러 곳에 따로 구현했고 그중 일부가 낡은 것" 이었다.
    주석에는 "동일" 이라 적혀 있었다. 주석은 거짓말을 한다. 코드를 직접 본다.

찾는 것
  A. 판정 로직 중복      제출 도구와 같은 일을 하는 코드가 따로 있는가
  B. 읽는데 없는 경로     읽으려는 파일이 지금 존재하는가 (쓰는 경로는 없어도 정상이라 뺀다)
  C. 산출물 신선도        생성물이 그 입력보다 오래됐는가 (검수 탭이 09-08 에 멈춰 있던 것을 이걸로 잡는다)
  D. 아무도 안 부르는 것

읽기/쓰기 구분
    앞 판은 make_full.py 의 출력 폴더를 "없는 경로" 로 잘못 짚었다.
    같은 줄에 mkdir·write·OUT·DST 가 있으면 쓰는 쪽으로 보고 넘어간다.
"""
import re
import subprocess
from collections import defaultdict
from pathlib import Path

V = Path(".")
SKIP = ("/.venv/", "/_archive/", "/__pycache__/", "/node_modules/")
AUTH = "_kisa_port/tools/kisa_items.py"


def files():
    out = []
    for p in list(V.glob("*.py")) + list((V / "scripts").rglob("*.py")) + list((V / "dash_v2").glob("*.py")):
        if any(k in "/" + str(p).replace("\\", "/") for k in SKIP):
            continue
        out.append(p)
    return sorted(set(out))


ALL = files()
TEXT = {p: p.read_text(encoding="utf-8", errors="replace") for p in ALL}

REFS = ""
for pat in ("*.md", "*.yaml", "*.sh", "*.py", "*.js"):
    for p in V.rglob(pat):
        if any(k in "/" + str(p).replace("\\", "/") for k in SKIP):
            continue
        try:
            REFS += p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

print(f"검사 대상 파이썬 {len(ALL)}개\n")

print("=== A. 제출 도구와 같은 판정을 따로 구현한 곳")
MARK = {"침입·배회 판정": ("corners", "settle", "dwell"),
        "방화 창 규칙": ("hits", "window", "smoke"),
        "쓰러짐 SeqNet": ("need", "FALL_WIN", "seqnet")}
for label, keys in MARK.items():
    hit = [p for p in ALL if str(p).replace("\\", "/") != AUTH
           and sum(1 for k in keys if k.lower() in TEXT[p].lower()) >= 2]
    if hit:
        print(f"  [{label}]  " + ", ".join(str(p) for p in hit))
print("  (제출 도구를 import 하면 중복이 아니다. 복사해 뒀으면 언젠가 갈라진다)\n")

WRITE = re.compile(r"mkdir|\bwrite|\bdump\(|savefig|to_csv|OUT\b|DST\b|out_dir|outdir")
PATH_RE = re.compile(r'["\']((?:/NHNHOME|/home|data/[^"\']+|dumps/[^"\']+|configs/[^"\']+|model/[^"\']+|runs/[^"\']+))["\']')
print("=== B. 읽으려는데 없는 경로 (쓰는 경로는 뺐다)")
bad = defaultdict(list)
for p in ALL:
    for i, line in enumerate(TEXT[p].splitlines(), 1):
        if WRITE.search(line):
            continue
        for m in set(PATH_RE.findall(line)):
            if any(c in m for c in "*?{}%<>") or " " in m:
                continue
            if not (V / m).exists():
                bad[p].append(f"{i}: {m}")
for p, ms in sorted(bad.items()):
    print(f"  {p}")
    for m in ms[:4]:
        print(f"     {m}")
if not bad:
    print("  없음")
print()

print("=== C. 산출물이 입력보다 오래된 것")
GEN = [("dash_v2/dash_meta.json", ["dumps/intrusion_tile", "dumps/loiter_trk_id",
                                   "dumps/score_tl", "_kisa_port/tools/kisa_items.py"]),
       ("dash_v2/dataset_meta.json", ["data/학습데이터"]),
       ("results/MODELS.json", ["_kisa_port/weights/kisa"])]
for out, ins in GEN:
    o = V / out
    if not o.exists():
        print(f"  {out}: 없음"); continue
    ot = o.stat().st_mtime
    older = [i for i in ins if (V / i).exists() and (V / i).stat().st_mtime > ot]
    import time
    ds = time.strftime("%m-%d", time.localtime(ot))
    print(f"  {out} ({ds})" + (f"  <- {', '.join(older)} 보다 오래됨" if older else "  최신"))
print()

print("=== D. 어디서도 참조되지 않는 스크립트")
n = 0
for p in ALL:
    if p.name in ("model.py", "score_kisa.py", "config.py"):
        continue
    if REFS.count(p.name) + REFS.count(p.stem) <= 2:
        print(f"  {p}"); n += 1
if not n:
    print("  없음")
