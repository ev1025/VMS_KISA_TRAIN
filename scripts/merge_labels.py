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

    added, dup, conflict, skipped_eval = [], 0, [], 0
    for r in inc:
        if r.get("eval"):                       # 채점 전용 행은 학습 저장소에 넣지 않는다
            skipped_eval += 1
            continue
        if ident(r) in have:
            dup += 1
            continue
        if slot(r) in slots:
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

    print(f"들어온 곳: {inc}" + ("  (미리보기)" if a.dry else ""))
    total_add = 0
    for name in ("person", "fire", "image"):
        r = merge_hand(name, inc, a.dry, a.take_incoming)
        if r is None:
            continue
        total_add += r["추가"]
        print(f"  손라벨 {r['이름']:6s} 들어온 {r['들어온행']:5d} · 추가 {r['추가']:4d} · 중복 {r['중복']:5d}"
              f" · 충돌 {r['충돌']:3d} · eval제외 {r['제외:eval']:4d} -> 결과 {r['결과행']}행")
        for c in r["_충돌목록"]:
            print(f"      충돌: {c}")
    r = merge_auto(inc, a.dry)
    if r:
        print(f"  자동라벨  새 클립 {r['새 클립']} · 추가된 프레임 {r['추가된 프레임']}")
        total_add += r["추가된 프레임"]
    print(f"\n{'추가될' if a.dry else '추가한'} 것 합계 {total_add}건")
    if a.dry:
        print("실제로 합치려면 --dry 를 빼고 다시 실행하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
