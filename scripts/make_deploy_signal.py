# -*- coding: utf-8 -*-
"""검수 재생바에 그릴 '배포 구성' 신호를 만든다.

왜 (2026-09-16)
    재생바의 불·연기 곡선이 dumps/score_tl/human_full.json 을 그리고 있었다.
    human_full 은 옛 실험이고 지금 배포는 두 가중치 앙상블이다(10편 82.35 대 100.00).
    화면이 판정 근거와 다른 모델을 보여 주면 검수가 검수가 아니다.

어떻게
    새로 추론하지 않는다. 앙상블은 '표본마다 두 모델의 최고 신뢰도' 이므로
    두 덤프를 원소별 max 로 합치면 그대로 배포 신호가 된다.
    _kisa_port/tools/kisa_items.py 의 ITEMS["fire"] 에서 어떤 실험인지 읽어 온다.

출력: dumps/score_tl/_deploy.json  (형식은 다른 덤프와 같다: {클립: {rows: [[t, 불, 연기]], gt: 초}})
"""
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
import kisa_items as K   # noqa: E402

TL = V / "dumps/score_tl"
# 배포 가중치 파일 -> 그 가중치를 낸 실험(덤프 이름). 새 가중치를 걸면 여기에 한 줄 추가한다.
WEIGHT_TO_EXP = {
    "fire_fog.pt": "fresh_48k_wildall_20260909",
    "fire_small.pt": "s2_s960_20260913",
    "fire_snowfull.pt": "g_wildpos_20260912",
}


def parts():
    cfg = K.ITEMS["fire"]
    names = [cfg["model"]] + ([cfg["model2"]] if cfg.get("model2") else [])
    out = []
    for n in names:
        exp = WEIGHT_TO_EXP.get(n)
        if not exp:
            raise SystemExit(f"{n} 이 어느 실험에서 왔는지 모른다. WEIGHT_TO_EXP 에 추가해라.")
        f = TL / (exp + ".json")
        if not f.is_file():
            raise SystemExit(f"덤프가 없다: {f}")
        out.append((exp, json.loads(f.read_text(encoding="utf-8"))))
    return out


def main():
    ps = parts()
    print("배포 구성:", " + ".join(e for e, _ in ps))
    base = ps[0][1]
    merged = {}
    for stem, e in base.items():
        rows = {round(r[0], 2): [r[1], r[2]] for r in e["rows"]}
        for _, other in ps[1:]:
            for r in (other.get(stem) or {}).get("rows", []):
                k = round(r[0], 2)
                if k in rows:
                    rows[k][0] = max(rows[k][0], r[1])
                    rows[k][1] = max(rows[k][1], r[2])
                else:
                    rows[k] = [r[1], r[2]]
        merged[stem] = {"rows": [[t, v[0], v[1]] for t, v in sorted(rows.items())], "gt": e["gt"]}
    out = TL / "_deploy.json"
    out.write_text(json.dumps(merged), encoding="utf-8")

    for stem in sorted(merged):
        a = max(r[1] for r in base[stem]["rows"])
        b = max(r[1] for r in merged[stem]["rows"])
        mark = "  <= 올라감" if b > a + 0.01 else ""
        print(f"  {stem}  불 최고 {a:.3f} -> {b:.3f}{mark}")
    print(f"\n저장 {out}  ({len(merged)}편)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
