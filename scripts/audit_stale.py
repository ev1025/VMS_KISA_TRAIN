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

# 손으로 돌리는 도구. 아무도 안 부르는 것이 정상이라 D 에서 뺀다.
# 별도 구현이지만 '있어야 하는 것'. 왜 있어도 되는지 여기 적어 둔다.
# 화면(js)은 import 가 없다. 서버가 계산한 sa 를 쓰면 중복이 아니다.
JS_OK = "return row.sa"   # 주석에 이름만 적은 것은 예외가 아니다. 실제로 그 값을 쓰는 코드여야 한다
KNOWN_DUP = {
    "score_kisa.py": "덤프(dumps/score_tl)를 만드는 쪽. 제출 경로와 같은 값이 나오는지 "
                     "scripts/fire_weight_check.py 로 대조한다. 규칙 상수는 kisa_items 와 같아야 한다.",
    "fire_rule2.py": "신규칙의 원본 설계. 참고용이고 채점에 반영되지 않는다.",
    "fall_track.py": "쓰러짐 SeqNet 학습기. 학습 쪽 코드라 판정기 중복이 아니다.",
}
HAND_TOOLS = {
    "audit_stale.py", "check_repro.py", "check_thor.py", "check_layout.py",
    "fire_weight_check.py", "fail_probe3.py", "merge_labels.py", "weather_aug.py",
    "build_coco_person.py", "build_snowfog_set.py", "find_snowfog.py",
    "server_pdump.py", "server_kptdump.py", "server_tdump.py",
    "01_build_manifest.py", "02_subsample_split.py", "04_convert_to_yolo.py",
    "patch_aihubshell.py", "serve_kisa.py", "build_dash_meta.py", "build_dataset_meta.py",
}
# 아직 안 만들었어도 정상인 산출물. 없다고 해서 코드가 낡은 것이 아니다.
OPTIONAL = {
    "data/학습데이터/손라벨/full/meta.json", "data/학습데이터/손라벨/full",
    # build_dataset_meta.py 가 훑는 학습셋. 학습을 마치고 지웠다(구성은 results/MODELS.json 에 옮겨 적음).
    # 없으면 그 탭을 건너뛰도록 만들어져 있으므로 없는 것이 정상이다.
    "data/학습데이터/aihub71751_24k", "data/학습데이터/human_synth",
    "data/학습데이터/person_v3", "data/학습데이터/aihub_int_pl",
}


def files():
    """검사 대상. 화면(js)도 판정을 하는 곳이라 같이 본다.
    2026-09-16: 파이썬만 보다가 dash_v2/js/core.js 의 낡은 판정 구현을 놓쳤다."""
    out = []
    for p in (list(V.glob("*.py")) + list((V / "scripts").rglob("*.py"))
              + list((V / "dash_v2").glob("*.py")) + list((V / "dash_v2/js").glob("*.js"))):
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

print("검사 대상", len(ALL), "개 · 파이썬",
      sum(1 for q in ALL if q.suffix == ".py"), "· 화면 js",
      sum(1 for q in ALL if q.suffix == ".js"))
print()

print("=== A. 제출 도구와 같은 판정을 따로 구현한 곳")
MARK = {"침입·배회 판정": ("corners", "settle", "dwell"),
        "방화 창 규칙": ("hits", "window", "smoke"),
        "쓰러짐 SeqNet": ("need", "FALL_WIN", "seqnet")}
# 화면(js)용 표지. window·hits 는 브라우저 전역·클릭 판정에도 쓰여 그대로 보면 전부 걸린다.
# 규칙 상수로만 쓰이는 낱말을 본다.
MARK_JS = {"침입·배회 판정": ("CORNERS", "SETTLE", "DWELL"),
           "방화 창 규칙": ("FTH", "RISE", "HIT"),
           "쓰러짐 SeqNet": ("NEED", "TH", "curves")}
for label, keys in MARK.items():
    jk = MARK_JS.get(label, keys)
    hit = [p for p in ALL if str(p).replace("\\", "/") != AUTH
           and p.name != "audit_stale.py"                      # 이 파일은 낱말만 들고 있다
           and "kisa_items as" not in TEXT[p]                  # 제출 도구를 불러 쓰면 중복이 아니다
           and not (p.suffix == ".js" and JS_OK in TEXT[p])    # 화면은 서버가 준 sa 를 쓰면 된다
           and "from kisa_items import" not in TEXT[p]          # (주석에 이름만 적은 것은 예외가 아니다)
           and sum(1 for k in (jk if p.suffix == ".js" else keys)
                   if (k in TEXT[p] if p.suffix == ".js" else k.lower() in TEXT[p].lower())) >= 2]
    real = [p for p in hit if p.name not in KNOWN_DUP]
    known = [p for p in hit if p.name in KNOWN_DUP]
    if real:
        print(f"  [{label}]  " + ", ".join(str(p) for p in real) + "   <-- 확인 필요")
    for p in known:
        print(f"  [{label}]  {p}  (알려진 것) {KNOWN_DUP[p.name]}")
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
            if m in OPTIONAL:
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
# 입력은 '그 산출물이 실제로 읽는 것' 만 적는다.
# dumps/score_tl 폴더 전체를 넣었더니 새 실험 덤프가 하나 생길 때마다 헛경보가 났다.
# 화면 곡선이 읽는 것은 배포 구성을 합친 _deploy.json 하나다(2026-09-16).
GEN = [("dash_v2/dash_meta.json", ["dumps/intrusion_tile_v3", "dumps/loiter_botsort_v2",
                                   "dumps/score_tl/_deploy.json", "dumps/fall_seq_1280",
                                   "_kisa_port/tools/kisa_items.py"]),
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
    if p.suffix == ".js":                       # 화면 파일은 dashboard.html 이 불러온다
        continue
    if p.name in ("model.py", "score_kisa.py", "config.py") or p.name in HAND_TOOLS:
        continue
    if REFS.count(p.name) + REFS.count(p.stem) <= 2:
        print(f"  {p}"); n += 1
if not n:
    print("  없음")
