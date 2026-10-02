# -*- coding: utf-8 -*-
"""사람 객체 인식 F1 을 구역(침입 · 배회 영역) 안 사람만으로 잰다(2026-10-02, 사용자: 영역 밖 작은 사람을 잡아도 오검으로 치지 말자).
평가셋 = build_evalset.py 가 만든 evalset_intrusion · evalset_loitering(배포 검증영상 라벨, 측정 전용).
구역 = 영역파일(zone_maps/<장소>.map)의 <Intrusion> · <Loitering> 다각형. 박스의 발끝(아래 가운데)으로 안 · 밖을 가른다(판정기와 같은 기준).
  안   : 발끝을 좌우로 MARGIN px 옮겨도 둘 다 구역 안
  밖   : 발끝 · 좌우 MARGIN px 세 점 모두 구역 밖
  경계 : 그 사이(어느 쪽으로도 안 셈)
매칭(사진마다, 확신도 높은 예측부터, IoU 0.5 이상 정답 하나와 짝):
  짝지은 정답이 안 → 정검, 경계 · 밖 → 안 셈(구역 밖 사람을 맞게 찾은 것)
  짝 없는 예측이 안 → 오검, 경계 · 밖 → 안 셈
  짝 없는 안 정답 → 미검
확신도 문턱을 훑어 최고 F1 과 그때 문턱, 문턱 0.40(판정기 침입) · 0.30(배회 규칙 B) 에서의 F1 을 낸다. 전체 화면 추론(침입 판정기의 3x3 칸 나눔은 아님)
  python scripts/det_f1_zone.py <가중치.pt> [<가중치.pt> ...] --imgsz 1280 [--items intrusion loitering]
  python scripts/det_f1_zone.py --selfcheck"""
import argparse
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
MARGIN = 10.0
IOU = 0.5


def in_poly(x, y, poly):
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def where(box, poly, m=MARGIN):
    """'in' · 'out' · 'edge'. box = (x1, y1, x2, y2) 픽셀"""
    cx, y = (box[0] + box[2]) / 2, box[3]
    pts = [in_poly(cx - m, y, poly), in_poly(cx, y, poly), in_poly(cx + m, y, poly)]
    return "in" if pts[0] and pts[2] else ("out" if not any(pts) else "edge")


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def score_image(gts, preds, poly):
    """gts = [box], preds = [(conf, box)]. 반환 (점수 매긴 예측 [(conf, 1=정검/0=오검)], 안 정답 수)"""
    gw = [where(g, poly) for g in gts]
    used = [False] * len(gts); out = []
    for c, p in sorted(preds, key=lambda x: -x[0]):
        best, bi = 0.0, -1
        for i, g in enumerate(gts):
            if not used[i]:
                v = iou(p, g)
                if v > best:
                    best, bi = v, i
        if best >= IOU:
            used[bi] = True
            if gw[bi] == "in":
                out.append((c, 1))
        elif where(p, poly) == "in":
            out.append((c, 0))
    return out, sum(1 for w in gw if w == "in")


def summarize(scored, n_gt, at=(0.40, 0.30)):
    """scored = 모든 사진의 (conf, 정검?) · n_gt = 안 정답 합. 최고 F1 과 문턱별 F1"""
    s = sorted(scored, key=lambda x: -x[0]); tp = fp = 0; best = (0.0, 0.0, 0.0, 0.0, 1.0)
    for c, t in s:
        tp += t; fp += 1 - t
        p, r = tp / (tp + fp), tp / max(1, n_gt)
        f = 2 * p * r / (p + r) if p + r else 0.0
        if f > best[0]:
            best = (f, p, r, c, 0)
    res = {"정답(구역 안)": n_gt, "최고 F1": round(best[0], 3), "그때 정밀도": round(best[1], 3), "그때 재현율": round(best[2], 3), "그때 문턱": round(best[3], 3)}
    for a in at:
        tp = sum(t for c, t in scored if c >= a); fp = sum(1 - t for c, t in scored if c >= a)
        p, r = (tp / (tp + fp) if tp + fp else 0.0), tp / max(1, n_gt)
        res[f"F1@{a:.2f}"] = round(2 * p * r / (p + r) if p + r else 0.0, 3)
    return res


def selfcheck():
    poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert where((40, 10, 60, 50), poly) == "in" and where((140, 10, 160, 50), poly) == "out" and where((90, 10, 110, 50), poly) == "edge"
    gts = [(40, 10, 60, 50), (140, 10, 160, 50)]                          # 안 1명 · 밖 1명
    sc, n = score_image(gts, [(0.9, (41, 11, 61, 51)), (0.8, (141, 10, 160, 50)), (0.7, (10, 60, 30, 90)), (0.6, (300, 10, 320, 50))], poly)
    assert n == 1 and sc == [(0.9, 1), (0.7, 0)], sc                      # 밖 사람 맞힘 · 밖 헛검출은 안 셈, 안 헛검출은 오검
    r = summarize(sc, n)
    assert r["최고 F1"] == 1.0 and r["F1@0.40"] == round(2 * 0.5 * 1 / 1.5, 3), r
    print("자체 점검 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", nargs="*"); ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--items", nargs="+", default=["intrusion", "loitering"]); ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--device", default="0", help="0 = GPU, cpu = CPU(학습이 GPU 를 다 쓸 때)")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    sys.path.insert(0, str(V / "_kisa_port/tools"))
    import kisa_items as K
    from ultralytics import YOLO
    MAPS = V / "data/원본데이터/kisa_배포_검증영상/zone_maps"
    ZONE = {"intrusion": "Intrusion", "loitering": "Loitering"}
    sets = {}
    for it in a.items:
        D = V / "data/학습데이터" / f"evalset_{it}"
        imgs = [l.strip() for l in (D / "val.txt").read_text().splitlines() if l.strip()]
        sets[it] = imgs
    out = {}
    for w in a.weights:
        m = YOLO(w)
        for it, imgs in sets.items():
            scored, n_gt, polys = [], 0, {}
            for k in range(0, len(imgs), 16):
                chunk = imgs[k:k + 16]
                res = m.predict(chunk, imgsz=a.imgsz, conf=0.05, classes=[0], verbose=False, device=a.device)
                for p, r in zip(chunk, res):
                    h, wd = r.orig_shape
                    stem = Path(p).stem.rsplit("_", 1)[0]
                    poly = polys.get(stem) or polys.setdefault(stem, K.zone_of(MAPS, stem, ZONE[it], (wd, h)))
                    gts = []
                    for row in Path(p.replace("/images/", "/labels/").rsplit(".", 1)[0] + ".txt").read_text().split("\n"):
                        if row.strip():
                            _, cx, cy, bw, bh = map(float, row.split())
                            gts.append(((cx - bw / 2) * wd, (cy - bh / 2) * h, (cx + bw / 2) * wd, (cy + bh / 2) * h))
                    preds = [(float(b.conf[0]), tuple(float(v) for v in b.xyxy[0])) for b in r.boxes]
                    sc, n = score_image(gts, preds, poly)
                    scored += sc; n_gt += n
            res = summarize(scored, n_gt); res["사진"] = len(imgs); res["편"] = len(polys)
            out[f"{Path(w).parts[-4] if len(Path(w).parts) > 4 else w}|{Path(w).stem}|{it}"] = res
            print(Path(w).parts[-4], Path(w).stem, it, json.dumps(res, ensure_ascii=False), flush=True)
    return out


if __name__ == "__main__":
    main()
