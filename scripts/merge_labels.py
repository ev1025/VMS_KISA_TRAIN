# -*- coding: utf-8 -*-
"""다른 장비(Thor)에서 만든 라벨을 서버 저장소에 합친다. 중복은 넣지 않는다.

왜 필요한가
    Thor 에 라벨링 작업대를 세우면서 손라벨·전파 저장소가 두 벌이 됐다.
    Thor 에서 친 라벨이 서버로 오지 않으면 학습셋 재빌드가 그것을 모른다.

무엇을 중복으로 보나
    한 행의 정체성은 (clip, t, cls, obj, 좌표) 다. 좌표는 5자리로 반올림해 비교한다
    (편집기가 저장할 때마다 미세하게 달라지는 값 때문에 같은 박스가 다르게 보이는 것을 막는다).

      같은 정체성 · 모든 값 같음   -> 중복. 건너뛴다
      같은 (clip, t, obj) · 좌표 다름 -> 충돌. 기본은 서버 값을 지키고 목록에 남긴다
      서버에 없음                  -> 추가

    충돌을 자동으로 덮어쓰지 않는 이유: 어느 쪽이 최신인지 파일만 봐서는 알 수 없다.
    양쪽에서 같은 클립을 만졌다면 사람이 봐야 한다. --take-incoming 을 주면 들어온 값으로 덮는다.

안전장치
    - 합치기 전에 서버 저장소를 _backup/ 에 스냅샷으로 남긴다(편집기와 같은 규칙).
    - 서버에만 있는 행은 절대 지우지 않는다. 추가만 한다.
    - eval 표시가 붙은 행(채점 전용)은 들어와도 넣지 않는다. 학습 누수 방지.
    - --dry 로 무엇이 들어올지 먼저 볼 수 있다.

사용
    python scripts/merge_labels.py <들어온_폴더> [--dry] [--take-incoming]
      들어온_폴더 = 손라벨/ 과 자동라벨/ 을 담은 폴더 (Thor 의 data/학습데이터 와 같은 구조)
"""
import argparse
import json
import shutil
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kisa_paths as KP

V = KP.V
HAND = V / "data/학습데이터/손라벨"
AUTO = V / "data/학습데이터/자동라벨"
R = 5                                   # 좌표 반올림 자리


def ident(row):
    """행의 정체성. 같은 사람·같은 프레임·같은 박스인지 가른다."""
    return (row.get("clip"), row.get("t"), row.get("cls"), row.get("obj"),
            round(float(row.get("x", 0)), R), round(float(row.get("y", 0)), R),
            round(float(row.get("w", 0)), R), round(float(row.get("h", 0)), R))


def slot(row):
    """좌표를 뺀 자리. 같은 자리에 다른 박스가 오면 충돌이다."""
    return (row.get("clip"), row.get("t"), row.get("cls"), row.get("obj"))


def backup(path):
    if not path.is_file():
        return None
    d = path.parent / "_backup"
    d.mkdir(exist_ok=True)
    b = d / f"{path.stem}.{time.strftime('%Y%m%d_%H%M%S')}.merge_before.json"
    shutil.copyfile(path, b)
    return b


def merge_clip_state(incoming, dry, take_incoming):
    """클립 표시(기본/전파/손)와 전파 시작·종료(a/b)를 합친다. 클립 단위·항목 단위로 본다."""
    dst = HAND / "clip_state.json"
    src = incoming / "손라벨" / "clip_state.json"
    if not src.is_file():
        return None
    cur = json.loads(dst.read_text(encoding="utf-8")) if dst.is_file() else {}
    inc = json.loads(src.read_text(encoding="utf-8"))
    added, changed, kept = 0, 0, 0
    out = {k: dict(v) for k, v in cur.items()}
    for stem, sv in inc.items():
        if not isinstance(sv, dict):
            continue
        mine = out.setdefault(stem, {})
        for k in ("mark", "a", "b", "smoke"):
            if k not in sv:
                continue
            if k not in mine:
                mine[k] = sv[k]; added += 1
            elif mine[k] != sv[k]:
                if take_incoming:
                    mine[k] = sv[k]; changed += 1
                else:
                    kept += 1
        if not mine:
            out.pop(stem, None)
    if not dry:
        backup(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_suffix(".json.tmpmerge")     # 편집기가 같은 파일을 쓰는 장비에서도 찢기지 않게
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(dst)
    return {"추가": added, "덮음": changed, "이쪽유지": kept}


def merge_hand(name, incoming, dry, take_incoming):
    dst = HAND / f"{name}_labels.json"
    src = incoming / "손라벨" / f"{name}_labels.json"
    if not src.is_file():
        return None
    cur = json.loads(dst.read_text(encoding="utf-8")) if dst.is_file() else []
    inc = json.loads(src.read_text(encoding="utf-8"))

    have = {ident(r) for r in cur}
    slots = {}
    for r in cur:
        slots.setdefault(slot(r), []).append(r)

    # 한 자리에 박스가 여럿이면 어느 것이 어느 것인지 짝지을 수 없다.
    # 화재 라벨은 객체가 불·연기 둘뿐이라 한 프레임에 불을 2개 치면 같은 자리가 된다.
    # 그럴 때 충돌로 보면 두 번째 박스부터 조용히 버려지므로, 그냥 새 박스로 추가한다.
    inc_slots = {}
    for r in inc:
        inc_slots[slot(r)] = inc_slots.get(slot(r), 0) + 1
    pairable = lambda k: len(slots.get(k, ())) == 1 and inc_slots.get(k, 0) == 1

    added, dup, conflict, skipped_eval = [], 0, [], 0
    for r in inc:
        if r.get("eval"):                       # 채점 전용 행은 학습 저장소에 넣지 않는다
            skipped_eval += 1
            continue
        if ident(r) in have:
            dup += 1
            continue
        if slot(r) in slots and pairable(slot(r)):
            conflict.append(r)
            if take_incoming:
                for old in slots[slot(r)]:
                    cur.remove(old)
                cur.append(r); have.add(ident(r)); added.append(r)
            continue
        cur.append(r); have.add(ident(r)); slots.setdefault(slot(r), []).append(r); added.append(r)

    res = {"이름": name, "들어온행": len(inc), "추가": len(added), "중복": dup,
           "충돌": len(conflict), "제외:eval": skipped_eval, "결과행": len(cur)}
    if not dry and added:
        b = backup(dst)
        tmp = dst.with_suffix(".json.tmpmerge")
        tmp.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dst)
        res["백업"] = str(b.relative_to(V)) if b else None
    res["_충돌목록"] = [f"{r.get('clip')} t={r.get('t')} obj={r.get('obj')}" for r in conflict[:10]]
    return res


def merge_auto(incoming, dry):
    """SAM 전파 저장소. 클립별 JSON 이고 frames/polys/seeds 를 프레임 단위로 합친다.

    자동라벨/ 바로 아래에는 2026-09-09~10 에 남긴 보관 파일(목록 형식)이 섞여 있다.
    실제 저장소는 자동라벨/sam2/ 뿐이므로 거기만 본다."""
    src = incoming / "자동라벨" / "sam2"
    if not src.is_dir():
        return None
    added_f = added_c = 0
    for p in sorted(src.rglob("*.json")):
        rel = p.relative_to(src)
        dst = AUTO / "sam2" / rel
        inc = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(inc, dict):           # 목록 형식은 전파 결과가 아니다
            continue
        if not dst.is_file():
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(json.dumps(inc, ensure_ascii=False), encoding="utf-8")
            added_c += 1
            added_f += len((inc or {}).get("frames") or {})
            continue
        cur = json.loads(dst.read_text(encoding="utf-8"))
        n = 0
        for key in ("frames", "polys"):
            a, b = cur.get(key) or {}, (inc or {}).get(key) or {}
            for t, v in b.items():
                if t not in a:                  # 서버에 없는 시각만 넣는다. 있는 것은 건드리지 않는다
                    a[t] = v; n += 1
            cur[key] = a
        # seeds 는 {t, obj, box} 목록이다. (t, obj) 가 같은 것은 이미 있는 것으로 본다
        sa = list(cur.get("seeds") or [])
        keys = {(s.get("t"), s.get("obj")) for s in sa if isinstance(s, dict)}
        for s in ((inc or {}).get("seeds") or []):
            if isinstance(s, dict) and (s.get("t"), s.get("obj")) not in keys:
                sa.append(s); keys.add((s.get("t"), s.get("obj"))); n += 1
        cur["seeds"] = sa
        if n and not dry:
            backup(dst)
            dst.write_text(json.dumps(cur, ensure_ascii=False), encoding="utf-8")
        added_f += n
    return {"새 클립": added_c, "추가된 프레임": added_f}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("incoming", help="들어온 라벨 폴더(손라벨/ · 자동라벨/ 을 담은 곳)")
    ap.add_argument("--dry", action="store_true", help="합치지 않고 무엇이 들어올지만 본다")
    ap.add_argument("--take-incoming", action="store_true", help="충돌 시 들어온 값으로 덮는다(기본은 서버 값 유지)")
    a = ap.parse_args()
    inc = Path(a.incoming)
    if not inc.is_dir():
        print(f"폴더 없음: {inc}"); return 2

    # 화면에는 "무엇을 몇 건 보낼 수 있나"만 쓴다(사용자 요청 2026-09-16).
    KO = {"person": "사람 라벨", "fire": "화재 라벨", "image": "이미지 라벨"}
    rows, total_add, conflicts = [], 0, []
    for name in ("person", "fire", "image"):
        r = merge_hand(name, inc, a.dry, a.take_incoming)
        if r is None:
            continue
        total_add += r["추가"]
        conflicts += [(KO[name], c) for c in r["_충돌목록"]]
        if r["추가"]:
            rows.append((KO[name], f"{r['추가']:,}건"))
    rcs = merge_clip_state(inc, a.dry, a.take_incoming)
    if rcs and (rcs["추가"] or rcs["덮음"]):
        total_add += rcs["추가"]
        rows.append(("클립 표시·전파구간", f"{rcs['추가']:,}건" + (f" (덮음 {rcs['덮음']:,})" if rcs["덮음"] else "")))
    if rcs and rcs["이쪽유지"]:
        rows.append(("클립 표시·전파구간", f"값이 달라 이쪽 유지 {rcs['이쪽유지']:,}건 (--take-incoming 이면 덮는다)"))
    r = merge_auto(inc, a.dry)
    if r and r["추가된 프레임"]:
        total_add += r["추가된 프레임"]
        rows.append(("전파 프레임", f"{r['추가된 프레임']:,}건"))

    if not rows:
        print("보낼 것 없음")
    else:
        for name, cnt in rows:
            print(f"{name:9s} {cnt}")
        print(f"{'합계':9s} {total_add:,}건")
    if conflicts:
        keep = "들어온 값으로 덮음" if a.take_incoming else "이쪽 값 유지"   # 양쪽에서 돌리므로 장비 이름을 쓰지 않는다
        print(f"{'충돌':9s} {len(conflicts)}건 ({keep})")

    # 합치고 나면 같은 불에 박스가 두 겹 남는다. 양쪽 편집기에서 같은 불꽃을 따로 그린 것이라
    # 정체성(좌표)이 달라 중복으로 걸리지 않는다. 사람이 따로 돌리는 것을 잊으면 되살아나므로
    # 여기서 바로 정리한다(2026-09-22: 75개가 이렇게 들어가 있었다).
    if not a.dry:
        import dedup_fire_labels as D
        f = HAND / "fire_labels.json"
        if f.is_file():
            rows = json.loads(f.read_text(encoding="utf-8"))
            keep_rows, gone = D.dedup(rows)
            if gone:
                shutil.copy2(f, f.with_suffix(".json.dedup_before"))
                f.write_text(json.dumps(keep_rows, ensure_ascii=False), encoding="utf-8")
                print(f"{'중복박스':9s} {len(gone)}건 제거 (같은 프레임·같은 클래스·IoU 0.5 이상)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
