# -*- coding: utf-8 -*-
"""학습 데이터 조합(2026-10-02, 사용자 "각각 별도로 존재하고 학습할 때 조합해서 쓰는 방식").
모듈(데이터 묶음)은 한 번만 만들어 두고, 큐 yaml 의 compose 칸으로 학습 때 목록 파일(train.txt)을 짠다. 이미지를 복사하지 않는다.

큐 yaml 실험 항목 예(옛 base · extras · oversample 대신):
  compose:
    use: [mod_person_coco_pos_20260927, mod_person_own_pos_20260927, mod_person_own_empty_20260927, mod_person_coco_empty_20260927]
    exclude: [flt_person_thin_20260930, flt_coco_crowd_20260930]        # 이미지 이름 목록. 이 사진들은 뺀다
    background: {ratio: 0.10, pool: [mod_person_coco_empty_20260927], prefer: [flt_coco_fence_20261001], seed: 0}
    repeat: {mod_person_own_pos_20260927: 2}                             # 반복(오버샘플). use 안 모듈은 모두 합쳐 k번
  val_set: data/학습데이터/trainset_person_hnfix_20260927/val_domain.txt  # compose 판은 검증셋을 꼭 적는다

순서
  1. use 모듈 목록을 차례로 이어 붙인다(같은 이미지 이름은 처음 것만)
  2. exclude 목록의 이름을 뺀다(repeat 로 더하는 것에도 똑같이)
  3. background 가 있으면: 라벨 있는 사진(양성)은 전부 두고, pool 모듈의 빈 사진만 골라 배경 비율을 맞춘다
       배경 = pool 밖의 빈 사진(우리 영상 빈 프레임 등, 전부 둠) + pool 에서 고른 빈 사진
       고를 장수 = round(양성 / (1 - ratio) * ratio) - pool 밖 빈 사진
       prefer 목록에 든 pool 사진을 먼저 넣고, 모자라면 나머지 pool 에서 random.Random(seed).sample 로 채운다
       (prefer 가 고를 장수보다 많으면 prefer 안에서 같은 방식으로 뽑는다)
  4. repeat: use 안 모듈은 (k - 1) 번 더, use 밖 모듈은 k 번 붙인다
모듈 이름 = data/학습데이터/<이름>/list.txt(목록 모듈 · 걸러 내기) 또는 보통 학습셋 폴더(러너 find_dataset · list_images 규칙).
배경 10% 셋(trainset_person_hnfix_full_bg10_20260928)은 위 규칙으로 한 장도 안 틀리고 다시 만들어진다(--check)."""
import json
import random
import sys
from pathlib import Path

KEYS = {"use", "exclude", "background", "repeat"}


def has_label(p):
    q = Path(p.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt")
    return q.exists() and bool(q.read_text().strip())


def compose(spec, resolve, labeled=has_label):
    """spec = 큐 yaml 의 compose 칸. resolve(이름) = 그 모듈의 줄 목록(이미지 경로 또는 이름).
    반환 (목록, 보고). labeled(경로) = 라벨이 있으면 True(시험용으로 바꿀 수 있게 인자)."""
    bad = set(spec) - KEYS
    assert not bad, f"compose 에 모르는 칸 {bad} (쓸 수 있는 칸 {sorted(KEYS)})"
    use = list(spec.get("use") or [])
    assert use, "compose.use 가 비었다"
    name = lambda p: Path(p).name
    flt = {f: {name(x) for x in resolve(f)} for f in spec.get("exclude") or []}
    drop = set().union(*flt.values()) if flt else set()
    rep = {"use": {}}
    items, seen, src, dropped = [], set(), {}, set()
    for m in use:
        got = resolve(m); n_in = 0
        for p in got:
            k = name(p)
            if k in seen:
                continue
            seen.add(k)
            if k in drop:
                dropped.add(k)
                continue
            items.append(p); src[k] = m; n_in += 1
        rep["use"][m] = {"모듈 장수": len(got), "들어간 장수": n_in}
    if flt:
        rep["exclude"] = {f: len(v & dropped) for f, v in flt.items()}      # 걸러 내기 목록마다 실제로 뺀 장수(겹치면 양쪽에 셈)
    bg = spec.get("background")
    if bg:
        ratio = float(bg["ratio"]); assert 0 < ratio < 1, ratio
        pool = set(bg.get("pool") or [])
        assert pool and pool <= set(use), "background.pool 은 use 안의 모듈이어야 한다"
        prefer = set()
        for f in bg.get("prefer") or []:
            prefer |= {name(x) for x in resolve(f)}
        pos = [p for p in items if labeled(p)]
        posset = set(pos)
        neg = [p for p in items if p not in posset]
        keep_neg = [p for p in neg if src[name(p)] not in pool]
        pool_neg = [p for p in neg if src[name(p)] in pool]
        want = round(len(pos) / (1 - ratio) * ratio) - len(keep_neg)
        assert want >= 0, f"pool 밖 빈 사진({len(keep_neg)})만으로 배경 비율 {ratio} 를 넘는다"
        pref = [p for p in pool_neg if name(p) in prefer]
        rest = [p for p in pool_neg if name(p) not in prefer]
        rng = random.Random(int(bg.get("seed", 0)))
        if want <= len(pref):
            chosen = set(rng.sample(pref, want))
        else:
            chosen = set(pref) | set(rng.sample(rest, min(want - len(pref), len(rest))))
        pool_set = set(pool_neg)
        items = [p for p in items if p in posset or p not in pool_set or p in chosen]
        n_bg = len(items) - len(pos)
        rep["background"] = {"양성": len(pos), "pool 밖 빈 사진": len(keep_neg), "pool 에서 고른 빈 사진": len(chosen),
                             "그중 prefer": len(chosen & set(pref)), "pool 에서 안 고른 빈 사진": len(pool_neg) - len(chosen),
                             "배경 비율": round(n_bg / len(items), 4)}
    out = list(items)
    in_use = {}
    for p in items:
        in_use.setdefault(src[name(p)], []).append(p)
    for m, k in (spec.get("repeat") or {}).items():
        k = int(k); assert k >= 1, (m, k)
        if m in use:
            out += in_use.get(m, []) * (k - 1)
        else:
            extra = [p for p in resolve(m) if name(p) not in drop]
            out += extra * k
        rep.setdefault("repeat", {})[m] = k
    rep["최종 장수"] = len(out)
    return out, rep


def selfcheck():
    """작은 가짜 모듈로 규칙을 확인한다(파일 안 읽음)"""
    mods = {"pos": [f"/x/images/p{i}.jpg" for i in range(90)], "own_e": ["/x/images/o0.jpg", "/x/images/o1.jpg"],
            "coco_e": [f"/x/images/c{i}.jpg" for i in range(40)], "fence": [f"c{i}.jpg" for i in range(5)],
            "thin": ["p0.jpg", "p1.jpg"], "kisa": [f"/x/images/k{i}.jpg" for i in range(3)]}
    lab = lambda p: Path(p).name[0] in "pk"
    R = lambda n: mods[n]
    out, rep = compose({"use": ["pos", "own_e", "coco_e"], "background": {"ratio": 0.1, "pool": ["coco_e"], "seed": 0}}, R, lab)
    assert rep["background"]["양성"] == 90 and len(out) == 100 and rep["background"]["pool 에서 고른 빈 사진"] == 8, rep
    out, rep = compose({"use": ["pos", "own_e", "coco_e"], "exclude": ["thin"], "background": {"ratio": 0.1, "pool": ["coco_e"], "prefer": ["fence"]}}, R, lab)
    nm = {Path(p).name for p in out}
    assert "p0.jpg" not in nm and {f"c{i}.jpg" for i in range(5)} <= nm and len(out) == 88 + 2 + round(88 / 0.9 * 0.1) - 2, (len(out), rep)
    out, rep = compose({"use": ["pos"], "repeat": {"pos": 2, "kisa": 3}}, R, lab)
    assert len(out) == 90 * 2 + 9, len(out)
    try:
        compose({"use": ["pos"], "oversample": {}}, R, lab); raise SystemExit("모르는 칸을 못 잡음")
    except AssertionError:
        pass
    print("compose 자체 점검 통과")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        selfcheck()
