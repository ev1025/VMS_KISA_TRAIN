# -*- coding: utf-8 -*-
"""ML → 대시보드 계약 점검(읽기 전용. dash_v2 모듈은 import 하지 않음).

python scripts/check_contract.py              → 저장소 점검. 위반이 있으면 종료 코드 1
python scripts/check_contract.py --selfcheck  → 파일 없이 자체 점검(깨진 문서는 걸리고 멀쩡한 문서는 통과)

보는 것: configs/result_blocks.yaml 의 phases 표 · 블록, results/*/meta.json 의 phase,
configs/history.yaml 항목, dumps/review 캐시 유무(표만, 위반 아님),
ml_changelog.md 맨 위 vN ↔ dash_v2/serve_kisa.py CONTRACT_VER(상수가 없으면 경고만).
저장소 루트 = 환경변수 VMS_ROOT, 없으면 이 파일의 부모의 부모(scripts/ 안에 있으므로)."""
import contextlib
import io
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("VMS_ROOT") or Path(__file__).resolve().parents[1])
HS_ST = ("완료", "진행", "할 일")                    # 히스토리 상태(계약 v3: 아이디어를 없앰, 전부 할 일)
HS_DEC = ("채택", "기각", "보류")                    # 판정. 완료 항목에만
HS_ITEM = ("방화", "사람", "쓰러짐", "공통")          # 히스토리 item(선택 키)
ITEM_DIRS = {"사람": ("intrusion", "loitering"), "침입": ("intrusion",), "배회": ("loitering",),
             "방화": ("fire",), "쓰러짐": ("falldown",)}   # meta.item → dumps/review 의 <item> 폴더
RE_ENTRY = re.compile(r"^## v(\d+)\b.*$", re.M)       # changelog 항목 머리 '## vN · 날짜 · 제목'
RE_HEAD = re.compile(r"^계약 버전: v(\d+)", re.M)      # changelog 머리줄
RE_VER = re.compile(r"^CONTRACT_VER\s*=\s*(\d+)", re.M)  # serve_kisa.py 상수


def check_phases(blocks_doc):
    """1. result_blocks.yaml 최상위 phases: 비어 있지 않은 문자열 → 문자열 사전"""
    ph = blocks_doc.get("phases")
    if not isinstance(ph, dict) or not ph:
        return ["result_blocks.yaml: 최상위 phases 표가 없음"]
    return [f"result_blocks.yaml: phases[{k!r}] = {v!r} 는 문자열 → 문자열이 아님"
            for k, v in ph.items() if not (isinstance(k, str) and isinstance(v, str))]


def check_metas(metas, phases):
    """2. results/<실험>/meta.json: phase 는 없거나 phases 코드. (phase, item, status) 수를 표로 찍음"""
    bad, cnt = [], Counter()
    for name, m in metas.items():
        ph = m.get("phase")
        if ph is not None and ph not in phases:
            bad.append(f"results/{name}/meta.json: phase={ph!r} 는 phases 에 없음")
        cnt[(ph or "없음", m.get("item") or "없음", str(m.get("status") or "없음"))] += 1
    for (ph, it, st), n in sorted(cnt.items()):
        print(f"  {ph:8} {it:4} {st:14} {n}")
    return bad


def check_blocks(blocks_doc, metas):
    """3. 블록마다 control ∈ runs. 블록 단계 = 블록의 phase(선택 키), 없으면 견주는 실험(대조군 제외) meta.phase 가 모두 같을 때 그 값
    (표: 블록 id → 단계 또는 없음). 화면 규칙 dash_v2 results_newdata.block_phase 와 같다(10-01). 대조군은 앞 단계 판일 수 있어 쓰지 않는다.
    적은 phase 는 phases 코드여야 하고, 견주는 실험의 공통 단계와 다르면 위반"""
    phases = blocks_doc.get("phases") if isinstance(blocks_doc.get("phases"), dict) else {}
    bad = []
    for b in blocks_doc.get("blocks") or []:
        bid, ctrl = b.get("id"), b.get("control")
        if ctrl not in (b.get("runs") or {}):
            bad.append(f"블록 {bid}: control={ctrl!r} 가 runs 에 없음")
        if b.get("phase") is not None and b["phase"] not in phases:
            bad.append(f"블록 {bid}: phase={b['phase']!r} 는 phases 에 없음")
        own = {(metas.get(x) or {}).get("phase") for x in (b.get("runs") or {}) if x != ctrl}
        common = own.pop() if len(own) == 1 else None
        if b.get("phase") and common and b["phase"] != common:
            bad.append(f"블록 {bid}: phase={b['phase']!r} 인데 견주는 실험의 단계는 {common!r}")
        ph = b.get("phase") or common
        print(f"  {str(bid):40} {ph or '없음'}")
    return bad


def check_history(doc, phases):
    """4. history.yaml: id · t 필수, s ∈ HS_ST, dec 는 완료 항목에만 HS_DEC, item ∈ HS_ITEM, phase ∈ phases,
    id 중복 · 날짜 중복 없음. 상태별 · 항목별 수를 찍음"""
    bad, ids, dates, st, it = [], Counter(), Counter(), Counter(), Counter()
    for day in doc.get("days") or []:
        dates[str(day.get("date"))] += 1
        for x in day.get("items") or []:
            tag = f"히스토리 {x.get('id') or '(id 없음)'}"
            if not x.get("id") or not x.get("t"):
                bad.append(f"{tag}: id 또는 t 가 없음")
            if x.get("s") not in HS_ST:
                bad.append(f"{tag}: s={x.get('s')!r} 는 {HS_ST} 밖")
            if x.get("dec") and (x.get("s") != "완료" or x["dec"] not in HS_DEC):
                bad.append(f"{tag}: dec={x['dec']!r} 는 완료 항목에만, 값은 {HS_DEC}")
            if x.get("item") and x["item"] not in HS_ITEM:
                bad.append(f"{tag}: item={x['item']!r} 는 {HS_ITEM} 밖")
            if x.get("phase") and x["phase"] not in phases:
                bad.append(f"{tag}: phase={x['phase']!r} 는 phases 에 없음")
            ids[x.get("id")] += 1
            st[x.get("s") or "없음"] += 1
            it[x.get("item") or "공통"] += 1
    bad += [f"히스토리 id 중복: {i} ×{n}" for i, n in ids.items() if n > 1]
    bad += [f"히스토리 날짜 중복: {d} ×{n}" for d, n in dates.items() if n > 1]
    print(f"  상태별 {dict(st)} · 항목별 {dict(it)}")
    return bad


def review_table(blocks_doc, metas, root):
    """5. 블록에 든 판마다 dumps/review/<판>/{best,last}/<item>/summary.json 유무 표. 위반 아님"""
    for b in blocks_doc.get("blocks") or []:
        for run in b.get("runs") or {}:
            items = ITEM_DIRS.get((metas.get(run) or {}).get("item"), ())
            cells = [f"{ck}/{it}:{'O' if (root / 'dumps' / 'review' / run / ck / it / 'summary.json').exists() else '-'}"
                     for ck in ("best", "last") for it in items]
            print(f"  {run:45} {' '.join(cells) or '(meta.item 모름)'}")
    return []


def check_changelog(md, serve_src):
    """6. ml_changelog.md 맨 위 vN = 머리 '계약 버전'. serve_kisa.py CONTRACT_VER = 확인 줄이 채워진 가장 높은 번호(상수가 없으면 경고만).
    '- 확인:' 이 빈 항목은 미확인 목록으로 찍고 위반으로 치지 않는다(풀스택 반영 대기)"""
    parts = RE_ENTRY.split(md)               # [머리, 번호, 본문, 번호, 본문, ...]
    if len(parts) < 3:
        return ["ml_changelog.md: '## vN · 날짜 · 제목' 항목이 없음"]
    bad, top = [], int(parts[1])
    head = RE_HEAD.search(md)
    if not head or int(head.group(1)) != top:
        bad.append(f"ml_changelog.md: 머리 '계약 버전' 이 맨 위 항목 v{top} 와 다름")
    ver = RE_VER.search(serve_src)
    if not ver:
        print(f"  경고: dash_v2/serve_kisa.py 에 CONTRACT_VER 없음(풀스택 반영 전). changelog 맨 위 = v{top}")
    pend = [f"v{parts[i]}" for i in range(1, len(parts), 2) if re.search(r"^- 확인:\s*$", parts[i + 1], re.M)]
    conf = max([int(parts[i]) for i in range(1, len(parts), 2) if f"v{parts[i]}" not in pend] or [0])   # 풀스택이 확인한 가장 높은 번호
    if ver and int(ver.group(1)) != conf:
        bad.append(f"serve_kisa.py CONTRACT_VER = {ver.group(1)} ≠ changelog 에서 확인된 가장 높은 번호 v{conf}")
    print(f"  미확인: {' · '.join(pend) or '없음'}")
    return bad


def load_yaml(p):
    """yaml → dict. 파일이 없으면 빈 dict(검사 쪽이 위반으로 잡음)"""
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.exists() else {}


def main():
    blocks_doc = load_yaml(ROOT / "configs" / "result_blocks.yaml")
    hist = load_yaml(ROOT / "configs" / "history.yaml")
    metas = {}
    for f in sorted((ROOT / "results").glob("*/meta.json")):
        try:
            metas[f.parent.name] = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"  경고: {f} 못 읽음 {e!r}")
    md_p, sv_p = ROOT / "ml_changelog.md", ROOT / "dash_v2" / "serve_kisa.py"
    md = md_p.read_text(encoding="utf-8") if md_p.exists() else ""
    serve_src = sv_p.read_text(encoding="utf-8") if sv_p.exists() else ""
    phases = blocks_doc.get("phases") if isinstance(blocks_doc.get("phases"), dict) else {}
    checks = [
        ("1 phases 표", lambda: check_phases(blocks_doc)),
        ("2 meta.phase (단계 · 항목 · 상태 · 수)", lambda: check_metas(metas, phases)),
        ("3 블록 control · 단계", lambda: check_blocks(blocks_doc, metas)),
        ("4 history.yaml", lambda: check_history(hist, phases)),
        ("5 검수 캐시 summary.json 유무(참고)", lambda: review_table(blocks_doc, metas, ROOT)),
        ("6 ml_changelog ↔ CONTRACT_VER", lambda: check_changelog(md, serve_src)),
    ]
    n_ok = n_bad = 0
    for name, fn in checks:
        print(f"[{name}]")
        bad = fn()
        for line in bad:
            print(f"  위반: {line}")
        n_bad += len(bad)
        n_ok += 0 if bad else 1
    print(f"{n_ok}개 통과 · {n_bad}개 위반")
    sys.exit(1 if n_bad else 0)


def selfcheck():
    """--selfcheck: 멀쩡한 문서는 위반 0, 깨진 문서는 각각 걸려야 한다. 파일은 읽지 않음"""
    phases = {"grid1": "1단계(해상도 × 배치 비교)"}
    ok_blocks = {"phases": phases, "blocks": [{"id": "b1", "control": "r1", "runs": {"r1": "대조군", "r2": "실험군"}}]}
    ok_metas = {"r1": {"item": "사람", "status": "trained", "phase": "grid1"}, "r2": {"item": "사람", "status": "trained"}}
    ok_hist = {"days": [{"date": "2026-10-01", "items": [
        {"id": "a1", "s": "완료", "dec": "채택", "t": "x", "item": "사람", "phase": "grid1"},
        {"id": "a2", "s": "할 일", "t": "y"}]}]}
    ok_md = "계약 버전: v2\n\n## v2 · 2026-10-01 · 둘\n- 확인: 2026-10-01 dash_v2 abc1234\n## v1 · 2026-10-01 · 하나\n- 확인:\n"
    ok_src = "PORT = 8890\nCONTRACT_VER = 2\n"

    def hist(*items):   # 하루짜리 히스토리 문서
        return {"days": [{"date": "2026-10-01", "items": list(items)}]}

    with contextlib.redirect_stdout(io.StringIO()):   # 표 출력은 숨김
        # 멀쩡한 쪽: 위반 0
        healthy = (check_phases(ok_blocks) + check_metas(ok_metas, phases) + check_blocks(ok_blocks, ok_metas)
                   + check_history(ok_hist, phases) + check_changelog(ok_md, ok_src))
        assert not healthy, healthy
        assert not check_changelog(ok_md, ""), "CONTRACT_VER 가 없으면 경고만 이어야 함"
        # 깨진 쪽: 하나씩 걸려야 함
        assert check_phases({"phases": None}), "phases 없음을 못 잡음"
        assert check_phases({"phases": {"grid1": 1}}), "phases 값이 문자열이 아닌 것을 못 잡음"
        assert check_metas({"r9": {"phase": "grid9"}}, phases), "meta 의 모르는 phase 를 못 잡음"
        assert check_blocks({"blocks": [{"id": "b", "control": "zz", "runs": {"r1": ""}}]}, ok_metas), "control ∉ runs 를 못 잡음"
        assert check_blocks({"phases": phases, "blocks": [{"id": "b", "phase": "grid9", "control": "r1", "runs": {"r1": ""}}]}, ok_metas), "블록의 모르는 phase 를 못 잡음"
        assert not check_blocks({"phases": phases, "blocks": [{"id": "b", "phase": "grid1", "control": "r1", "runs": {"r1": ""}}]}, ok_metas), "블록 phase 가 멀쩡한데 걸림"
        m2 = {"c": {"phase": "grid1"}, "x": {"phase": "grid2"}}
        assert check_blocks({"phases": {"grid1": "1", "grid2": "2"}, "blocks": [{"id": "b", "phase": "grid1", "control": "c", "runs": {"c": "", "x": ""}}]}, m2), "견주는 실험 단계와 다른 블록 phase 를 못 잡음"
        assert not check_blocks({"phases": {"grid1": "1", "grid2": "2"}, "blocks": [{"id": "b", "control": "c", "runs": {"c": "", "x": ""}}]}, m2), "대조군이 앞 단계인 2단계 묶음이 걸림"
        assert check_history(hist({"id": "a", "s": "진행", "dec": "채택", "t": "x"}), phases), "완료 아닌 항목의 dec 를 못 잡음"
        assert check_history(hist({"id": "a", "s": "완료", "dec": "확인 중", "t": "x"}), phases), "HS_DEC 밖 dec 를 못 잡음"
        assert check_history(hist({"id": "a", "s": "할 일", "t": "x"}, {"id": "a", "s": "할 일", "t": "y"}), phases), "id 중복을 못 잡음"
        assert check_history(hist({"id": "a", "s": "할 일", "t": "x", "item": "배회"}), phases), "item 집합 밖을 못 잡음"
        assert check_history(hist({"id": "a", "s": "할 일", "t": "x", "phase": "grid9"}), phases), "히스토리의 모르는 phase 를 못 잡음"
        assert check_history(hist({"id": "a", "s": "검토", "t": "x"}), phases), "HS_ST 밖 상태를 못 잡음"
        assert check_history({"days": [hist()["days"][0], hist()["days"][0]]}, phases), "날짜 중복을 못 잡음"
        assert check_changelog(ok_md, "CONTRACT_VER = 1\n"), "changelog ↔ CONTRACT_VER 불일치를 못 잡음"
        wait_md = "계약 버전: v3\n\n## v3 · d · t\n- 확인:\n## v2 · d · t\n- 확인: 2026-10-01 dash_v2 abc1234\n"
        assert not check_changelog(wait_md, ok_src), "확인 전 항목(v3)을 위반으로 침"
        assert check_changelog(wait_md, "CONTRACT_VER = 3\n"), "확인 줄 없이 CONTRACT_VER 만 올린 것을 못 잡음"
        assert check_history(hist({"id": "a", "s": "아이디어", "t": "x"}), phases), "없앤 상태(아이디어)를 못 잡음"
        assert check_changelog("계약 버전: v1\n\n## v2 · d · t\n- 확인:\n", ok_src), "머리 계약 버전 불일치를 못 잡음"
        assert check_changelog("아무 항목 없음\n", ok_src), "항목 없는 changelog 를 못 잡음"
    print("자체 점검 통과")


if __name__ == "__main__":
    selfcheck() if "--selfcheck" in sys.argv else main()
