# -*- coding: utf-8 -*-
"""운영 가중치가 전부 results/MODELS.json 에 적혀 있는지 검사한다.

왜 있는가: 2026-09-15 에 person_v2/v3 가 무슨 데이터로 학습됐는지 찾다가 결국
logs/_archive/*.gz 를 압축 해제해 뒤져서야 알아냈다. 기록이 runs/ · results/ · logs/
세 군데에 다른 방식으로 흩어져 있어서 생긴 일이다. 계보를 묻는 질문은 MODELS.json
한 곳만 보면 되게 하고, 새 가중치를 걸면서 기록을 빼먹는 것을 이 검사로 막는다.

  python3 scripts/check_models.py          검사만
  python3 scripts/check_models.py --fix    빠진 가중치의 빈 항목을 만들어 준다(내용은 사람이 채운다)

빠진 게 있으면 1 로 끝난다.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import kisa_paths as KP          # 경로는 여기 한 곳에서만 가져온다

WEIGHTS = KP.V / "_kisa_port/weights/kisa"      # 인증 실행이 실제로 읽는 폴더
MANIFEST = KP.V / "results/MODELS.json"


def sha16(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true", help="빠진 가중치의 빈 항목을 만든다")
    a = ap.parse_args()

    if not MANIFEST.is_file():
        print(f"[실패] {MANIFEST} 가 없다")
        return 1
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    models = man.get("models", {})

    live = sorted(p for p in WEIGHTS.glob("*.pt"))
    if not live:
        print(f"[실패] {WEIGHTS} 에 가중치가 없다")
        return 1

    bad = []
    for p in live:
        real = p.resolve()
        name = p.name
        entry = models.get(name)
        if entry is None:
            bad.append(f"{name}: MODELS.json 에 없다")
            if a.fix:
                models[name] = {"sha256_16": sha16(real) if real.is_file() else None,
                                "path": str(real).replace(str(KP.V.parent) + "/", ""),
                                "task": None, "used_by": [], "kisa_f1": {},
                                "base_model": None, "train": None,
                                "dataset": {"status": "record_missing", "note": "채울 것"},
                                "evidence": None, "note": "check_models.py --fix 가 만든 빈 항목"}
            continue
        if not real.is_file():
            bad.append(f"{name}: 심링크가 가리키는 파일이 없다 → {real}")
            continue
        got = sha16(real)
        want = entry.get("sha256_16")
        if want and want != got:
            bad.append(f"{name}: 내용이 바뀌었다 (기록 {want} · 실제 {got}). "
                       f"모델을 바꿨으면 MODELS.json 도 같이 고칠 것")

    # 기록에는 있는데 실물이 없는 항목(오래된 줄)
    for name in models:
        if not (WEIGHTS / name).exists():
            bad.append(f"{name}: MODELS.json 에만 있고 {WEIGHTS.name}/ 에는 없다")

    if a.fix and bad:
        man["models"] = models
        MANIFEST.write_text(json.dumps(man, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"[--fix] 빈 항목을 만들었다. {MANIFEST} 를 열어 내용을 채울 것")

    for b in bad:
        print("  [빠짐]", b)
    miss = [n for n, e in models.items()
            if (e.get("dataset") or {}).get("status") == "record_missing"]
    if miss:
        print(f"  [주의] 학습 기록이 없는 가중치: {', '.join(miss)}")
    print(f"운영 가중치 {len(live)}개 · 기록 {len(models)}개 · 문제 {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
