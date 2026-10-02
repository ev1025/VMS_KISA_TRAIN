# -*- coding: utf-8 -*-
"""학습 제외 목록(대시보드 입력 데이터 탭 X 단추) → 걸러 내기 모듈 flt_train_exclude_<날짜>/ (2026-10-02, ml_changelog 요청)
읽기  data/학습데이터/손라벨/train_exclude.json  {"items": [{set, path, name, why, by, at}]}  (대시보드 POST /api/train_exclude 만 씀)
쓰기  data/학습데이터/flt_train_exclude_<YYYYMMDD>/{list.txt, meta.json}  list.txt = 이미지 파일 이름 한 줄씩(compose exclude 키)
쓰는 법: 큐를 새로 짤 때 한 번 돌리고, 나온 이름을 그 큐 compose.exclude 에 적는다(러너가 자동으로 넣지 않는다: 큐 yaml 만 보고 무엇을 뺐는지 알 수 있게)
모듈은 고치지 않는다: 같은 이름 폴더가 있고 내용이 다르면 멈춘다 → --name 으로 새 이름
  python scripts/make_exclude_filter.py [--name flt_train_exclude_20261002b]
  python scripts/make_exclude_filter.py --selfcheck"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def build(src, out):
    """src 제외 목록 → out 폴더. 반환 (이름 수, 새로 만들었나). 같은 내용이 이미 있으면 그대로 둔다"""
    items = json.loads(Path(src).read_text(encoding="utf-8")).get("items") or []
    names = sorted({str(it["name"]).strip() for it in items if str(it.get("name", "")).strip()})
    assert names, "제외 목록이 비었다"
    text = "\n".join(names) + "\n"
    if (out / "list.txt").exists():
        assert (out / "list.txt").read_text(encoding="utf-8") == text, f"{out.name} 이 이미 있고 내용이 다르다 → --name 으로 새 이름(모듈은 고치지 않는다)"
        return len(names), False
    out.mkdir(parents=True)
    (out / "list.txt").write_text(text, encoding="utf-8")
    sets = sorted({str(it.get("set", "")) for it in items if it.get("set")})
    meta = {"name": out.name, "kind": "filter", "item": "공통", "built": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(names),
            "source": str(src), "sets": sets, "note": "대시보드 입력 데이터 탭에서 사람이 학습 제외로 누른 사진(why 가 비면 눈으로 뺀 것)"}
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(names), True


def selfcheck():
    t = Path(tempfile.mkdtemp())
    src = t / "train_exclude.json"
    src.write_text(json.dumps({"items": [{"set": "mod_a", "path": "/x/images/a.jpg", "name": "a.jpg"},
                                         {"set": "mod_b", "path": "/y/images/a.jpg", "name": "a.jpg"},
                                         {"set": "mod_a", "path": "/x/images/b.jpg", "name": "b.jpg"}]}), encoding="utf-8")
    out = t / "flt_train_exclude_20990101"
    assert build(src, out) == (2, True) and (out / "list.txt").read_text() == "a.jpg\nb.jpg\n"
    assert build(src, out) == (2, False)                                  # 같은 내용은 그대로
    src.write_text(json.dumps({"items": [{"name": "c.jpg"}]}), encoding="utf-8")
    try:
        build(src, out); raise SystemExit("내용이 다른데 덮어썼다")
    except AssertionError:
        pass
    print("자체 점검 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=None); ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    import kisa_paths as KP
    D = KP.V / "data/학습데이터"
    out = D / (a.name or time.strftime("flt_train_exclude_%Y%m%d"))
    src = D / "손라벨/train_exclude.json"
    if not src.is_file():
        print("제외 목록이 아직 없다(대시보드 입력 데이터 탭에서 학습 제외를 누른 적 없음). 뺄 것 없음")
        return
    n, new = build(src, out)
    print(f"{out.name}: 이름 {n}개 ({'새로 만듦' if new else '이미 같은 것이 있음'}) → 큐 compose.exclude 에 '{out.name}' 를 적는다")


if __name__ == "__main__":
    main()
