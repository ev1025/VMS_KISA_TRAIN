# -*- coding: utf-8 -*-
"""배포 검증영상 라벨 기준 객체 인식 F1. 모델 성능 비교의 기준값(2026-10-02 사용자 "이걸 기준으로 F1 을 구해 모델 성능을 측정").
IoU 기준(2026-10-02 사용자 "화재는 mAP50 기준 F1, 사람은 mAP50-95 기준 F1"): 방화 = IoU 0.5, 사람(침입 · 배회 · 쓰러짐) = IoU 0.50 ~ 0.95(0.05 간격 10단계)
  각 단계에서 따로 짝지어 F1 을 내고 평균한다(COCO mAP50-95 와 같은 방식). 최고 F1 = 확신도 문턱을 훑은 평균 F1 의 최댓값
평가셋 = build_evalset.py 가 만든 evalset_<항목>(배포 검증영상 사람 라벨, 측정 전용 · 학습 금지).
  라벨 범위(박스 있는 첫 ~ 끝 시각) 밖 = 대상 없음(2초 간격 빈 사진) → 거기서 나온 검출은 오검
  쓰러짐은 정답 -2 ~ +10초 창 안 사진만(창 밖에도 사람이 있어 '없음' 으로 못 쓴다)
항목별 규칙
  intrusion · loitering : 구역(영역파일 <Intrusion> · <Loitering>) 안 사람만 센다. 발끝을 좌우 10px 옮겨도 안이면 안, 셋 다 밖이면 밖, 그 사이는 경계(안 셈)
                          구역 밖 사람은 맞게 찾아도 · 헛검출이어도 안 센다(C00_047 오른쪽 위 작은 사람들)
  fire                  : 화면 전체, 불 · 연기 클래스별(클래스가 같아야 짝). 판정기는 불만 쓴다(연기 끔)
  falldown              : 화면 전체 사람, 편마다 재현율도 낸다(편 평균 = 장수 많은 편이 좌우하지 않게)
매칭: 사진마다 확신도 높은 예측부터, 같은 클래스 정답 중 IoU 가 그 단계 이상이고 가장 큰 것과 짝. 남은 예측 = 오검, 남은 정답 = 미검
  정밀도 · 재현율은 단계 평균, 오검 · 미검 수는 IoU 0.5 단계 값. 대상 없음 사진 오검은 IoU 와 무관
예측 저장: 가중치 · 항목 · 해상도 · 추론 방식마다 <out 폴더>/preds/*.json 에 남기고, 있으면 추론을 건너뛴다(지표만 바꿀 때 다시 안 돌림)
문턱: 판정기 값(침입 0.40 · 배회 0.30 · 불 0.40 · 쓰러짐 자세 0.10)에서의 F1 과, 문턱을 훑은 최고 F1 · 그때 문턱
추론: 기본은 전체 화면 한 장. --judge-infer 면 판정기와 같은 추론(2026-10-02): 침입 = 3x3 칸(겹침 0.2) 마다 --imgsz 로 키워 추론 ·
  확신도 0.15 이상 · IoU NMS(판정기 PersonDetector 그대로), 방화 = 6뷰(전체 + 4분할 + 가운데) 낱장 추론 뒤 클래스별 NMS(IoU 0.5).
  배회 · 쓰러짐 판정기는 원래 전체 화면이라 옵션과 상관없다. 해상도는 --imgsz(= 학습 해상도, 쓰러짐 자세 모델은 판정기와 같은 1280)
  python scripts/det_f1.py <가중치.pt ...> --items intrusion loitering --imgsz 1280 [--root <저장소>] [--tools <kisa_items 폴더>] [--device 0] [--out 결과.json]
  python scripts/det_f1.py --selfcheck
--root: 평가셋 · 영역파일이 있는 저장소 루트(다른 서버에서 돌릴 때). val.txt 의 경로는 'data/학습데이터/' 뒤만 붙여 바꾼다"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

V = Path(__file__).resolve().parents[1]
MARGIN = 10.0
IOU = 0.5
IOU_PERSON = tuple(round(0.5 + 0.05 * i, 2) for i in range(10))     # 0.50 ~ 0.95
ITEM = {"intrusion": dict(zone="Intrusion", classes=[0], names=["person"], at=(0.40,), ious=IOU_PERSON),
        "loitering": dict(zone="Loitering", classes=[0], names=["person"], at=(0.30,), ious=IOU_PERSON),
        "fire": dict(zone=None, classes=[0, 1], names=["fire", "smoke"], at=(0.40,), ious=(IOU,)),
        "falldown": dict(zone=None, classes=[0], names=["person"], at=(0.10, 0.25), ious=IOU_PERSON)}


def in_poly(x, y, poly):
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def where(box, poly, m=MARGIN):
    """'in' · 'out' · 'edge'. box = (x1, y1, x2, y2) 픽셀. poly 가 없으면 늘 'in'(화면 전체)"""
    if poly is None:
        return "in"
    cx, y = (box[0] + box[2]) / 2, box[3]
    pts = [in_poly(cx - m, y, poly), in_poly(cx, y, poly), in_poly(cx + m, y, poly)]
    return "in" if pts[0] and pts[2] else ("out" if not any(pts) else "edge")


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def score_image(gts, preds, poly, thr=IOU):
    """gts = [(cls, box)], preds = [(conf, cls, box)], thr = 짝짓는 IoU. 반환 ([(cls, conf, 1=정검/0=오검)], {cls: 안 정답 수})"""
    gw = [where(g, poly) for _, g in gts]
    used = [False] * len(gts); out = []
    for c, k, p in sorted(preds, key=lambda x: -x[0]):
        best, bi = 0.0, -1
        for i, (gk, g) in enumerate(gts):
            if not used[i] and gk == k:
                v = iou(p, g)
                if v > best:
                    best, bi = v, i
        if best >= thr:
            used[bi] = True
            if gw[bi] == "in":
                out.append((k, c, 1))
        elif where(p, poly) == "in":
            out.append((k, c, 0))
    n = {}
    for (gk, _), w in zip(gts, gw):
        if w == "in":
            n[gk] = n.get(gk, 0) + 1
    return out, n


def summarize(scored, n_gt, at):
    """scored = IoU 단계마다 [(conf, 정검?)] 목록 · n_gt = 안 정답 수. 단계 평균 F1 의 최고값과 문턱별 정밀도 · 재현율 · F1(단계 평균)"""
    import numpy as np
    grid = np.unique(np.array([c for x in scored for c, _ in x], dtype=float))[::-1]      # 확신도 문턱 후보(높은 것부터)
    curves = []                                                                             # 단계마다 문턱별 F1
    for x in scored:
        c = np.array([v[0] for v in x], dtype=float); t = np.array([v[1] for v in x], dtype=float)
        o = np.argsort(-c); c, t = c[o], t[o]
        k = np.searchsorted(-c, -grid, side="right")                                       # 문턱 이상인 예측 수
        tp, fp = np.concatenate([[0], np.cumsum(t)])[k], np.concatenate([[0], np.cumsum(1 - t)])[k]
        p, r = tp / np.maximum(tp + fp, 1), tp / max(1, n_gt)
        curves.append(np.where(p + r > 0, 2 * p * r / np.maximum(p + r, 1e-12), 0.0))
    f = np.mean(curves, axis=0) if len(grid) else np.zeros(0)
    i = int(np.argmax(f)) if len(f) else -1
    res = {"정답": n_gt, "최고 F1": round(float(f[i]), 3) if i >= 0 else 0.0, "그때 문턱": round(float(grid[i]), 3) if i >= 0 else 1.0}
    for a in at:
        fs, ps, rs = [], [], []
        for x in scored:
            tp = sum(t for c, t in x if c >= a); fp = sum(1 - t for c, t in x if c >= a)
            p, r = (tp / (tp + fp) if tp + fp else 0.0), tp / max(1, n_gt)
            fs.append(2 * p * r / (p + r) if p + r else 0.0); ps.append(p); rs.append(r)
        tp0 = sum(t for c, t in scored[0] if c >= a); fp0 = sum(1 - t for c, t in scored[0] if c >= a)
        res[f"@{a:.2f}"] = {"F1": round(sum(fs) / len(fs), 3), "정밀도": round(sum(ps) / len(ps), 3), "재현율": round(sum(rs) / len(rs), 3),
                            "F1(IoU 0.5)": round(fs[0], 3), "오검": fp0, "미검": n_gt - tp0}
    return res


def selfcheck():
    poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert where((40, 10, 60, 50), poly) == "in" and where((140, 10, 160, 50), poly) == "out" and where((90, 10, 110, 50), poly) == "edge"
    assert where((140, 10, 160, 50), None) == "in"
    gts = [(0, (40, 10, 60, 50)), (0, (140, 10, 160, 50))]                      # 안 1명 · 밖 1명
    sc, n = score_image(gts, [(0.9, 0, (41, 11, 61, 51)), (0.8, 0, (141, 10, 160, 50)), (0.7, 0, (10, 60, 30, 90)), (0.6, 0, (300, 10, 320, 50))], poly)
    assert n == {0: 1} and sc == [(0, 0.9, 1), (0, 0.7, 0)], sc                  # 밖 사람 맞힘 · 밖 헛검출은 안 셈, 안 헛검출은 오검
    r = summarize([[(c, t) for _, c, t in sc]], n[0], (0.40,))
    assert r["최고 F1"] == 1.0 and r["@0.40"]["F1"] == round(2 * 0.5 * 1 / 1.5, 3) and r["@0.40"]["오검"] == 1, r
    sc, n = score_image([(0, (0, 0, 10, 10)), (1, (50, 50, 90, 90))], [(0.9, 1, (0, 0, 10, 10)), (0.8, 1, (50, 50, 90, 90))], None)
    assert n == {0: 1, 1: 1} and sorted(sc) == [(1, 0.8, 1), (1, 0.9, 0)], sc    # 클래스가 다르면 짝이 아니다(불 자리의 연기 예측 = 오검)
    # IoU 단계 평균: 정답과 IoU 0.68 인 예측 하나 → 0.50 ~ 0.65(4단계) 정검, 0.70 ~ 0.95(6단계) 오검 → 평균 F1 = 4 / 10
    g = (0, 0, 100, 100); pb = (0, 0, 100, 68)
    assert abs(iou(pb, g) - 0.68) < 1e-6
    per = [score_image([(0, g)], [(0.9, 0, pb)], None, thr)[0] for thr in IOU_PERSON]
    r = summarize([[(c, t) for _, c, t in x] for x in per], 1, (0.40,))
    assert r["@0.40"]["F1"] == 0.4 and r["@0.40"]["F1(IoU 0.5)"] == 1.0 and r["최고 F1"] == 0.4, r
    print("자체 점검 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("weights", nargs="*"); ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--items", nargs="+", default=["intrusion", "loitering"], choices=list(ITEM))
    ap.add_argument("--root", default=str(V)); ap.add_argument("--tools", default=None)
    ap.add_argument("--device", default="0", help="0 = GPU, cpu = CPU(학습이 GPU 를 다 쓸 때)")
    ap.add_argument("--out", default=None); ap.add_argument("--selfcheck", action="store_true")
    ap.add_argument("--judge-infer", action="store_true", help="침입 3x3 칸 · 방화 6뷰로 판정기와 같게 추론(결과 이름 끝에 '|판정기추론')")
    a = ap.parse_args()
    if a.selfcheck:
        return selfcheck()
    R = Path(a.root)
    sys.path.insert(0, a.tools or str(R / "_kisa_port/tools"))
    import kisa_items as K
    from ultralytics import YOLO
    MAPS = R / "data/원본데이터/kisa_배포_검증영상/zone_maps"
    sets = {}
    for it in a.items:
        lines = [l.strip() for l in (R / "data/학습데이터" / f"evalset_{it}" / "val.txt").read_text().splitlines() if l.strip()]
        sets[it] = [str(R / "data/학습데이터" / l.split("data/학습데이터/", 1)[1]) for l in lines]
    out = {}
    for w in a.weights:
        wp = Path(w)
        name = f"{wp.parts[-4]}|{wp.stem}" if wp.parent.name == "weights" and len(wp.parts) > 4 and wp.parts[-3] != "kisa_eval" else wp.stem
        m = YOLO(w)
        pdet = K.PersonDetector(w, tile=dict(K.TILE, imgsz=a.imgsz), device=a.device, contain=None) if a.judge_infer and "intrusion" in sets else None

        def judge_preds(it, path):
            """판정기와 같은 추론. 반환 (높이, 너비, [(conf, cls, (x1, y1, x2, y2))])"""
            import cv2
            bgr = cv2.imread(path); h, wd = bgr.shape[:2]
            if it == "intrusion":
                return h, wd, [(c, 0, (x1, y1, x2, y2)) for c, x1, y1, x2, y2 in pdet.detect(bgr)]
            offs = [(0, 0), (0, 0), (wd // 2, 0), (0, h // 2), (wd // 2, h // 2), (wd // 4, h // 4)]
            crops = [bgr] + [bgr[y:y + h // 2, x:x + wd // 2] for x, y in offs[1:]]
            byc = {}
            for crop, (ox, oy) in zip(crops, offs):
                for b in m.predict(crop, conf=0.05, imgsz=a.imgsz, verbose=False, device=a.device)[0].boxes:
                    x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                    byc.setdefault(int(b.cls[0]), []).append((float(b.conf[0]), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
            return h, wd, [(c, k, (x1, y1, x2, y2)) for k, ds in byc.items() for c, x1, y1, x2, y2 in K.nms(ds, thr=0.5, contain=2.0)]
        for it, imgs in sets.items():
            cfg = ITEM[it]; ious = cfg["ious"]
            judge = a.judge_infer and it in ("intrusion", "fire")
            cache = Path(a.out or "det_f1.json").resolve().parent / "preds" / (
                f"{name.replace('|', '_')}_{it}_{a.imgsz}{'_judge' if judge else ''}_{hashlib.md5(Path(w).read_bytes()).hexdigest()[:8]}.json")
            saved = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else None
            got_all = {}
            scored = {k: [[] for _ in ious] for k in cfg["classes"]}; n_gt = {k: 0 for k in cfg["classes"]}
            clip = {}; polys = {}; n_neg = 0; neg_fp = {k: [] for k in cfg["classes"]}
            for i in range(0, len(imgs), 16):
                chunk = imgs[i:i + 16]
                if saved is not None:
                    got = [(h, wd, [(c, k, tuple(b)) for c, k, b in ps]) for h, wd, ps in (saved[Path(p).name] for p in chunk)]
                elif judge:
                    got = [judge_preds(it, p) for p in chunk]
                else:
                    got = [(*r.orig_shape, [(float(b.conf[0]), int(b.cls[0]), tuple(float(v) for v in b.xyxy[0])) for b in r.boxes])
                           for r in m.predict(chunk, imgsz=a.imgsz, conf=0.05, classes=cfg["classes"], verbose=False, device=a.device)]
                for p, (h, wd, preds) in zip(chunk, got):
                    got_all[Path(p).name] = (h, wd, preds)
                    stem = Path(p).stem.rsplit("_", 1)[0]
                    if cfg["zone"]:
                        poly = polys[stem] if stem in polys else polys.setdefault(stem, K.zone_of(MAPS, stem, cfg["zone"], (wd, h)))
                    else:
                        poly = None
                    gts = []
                    for row in (Path(p).parent.parent / "labels" / (Path(p).stem + ".txt")).read_text().split("\n"):   # images/x.jpg → labels/x.txt(윈도우 경로에서도)
                        if row.strip():
                            k, cx, cy, bw, bh = row.split(); cx, cy, bw, bh = map(float, (cx, cy, bw, bh))
                            gts.append((int(k), ((cx - bw / 2) * wd, (cy - bh / 2) * h, (cx + bw / 2) * wd, (cy + bh / 2) * h)))
                    for j, thr in enumerate(ious):
                        sc, n = score_image(gts, preds, poly, thr)
                        for k, c, t in sc:
                            scored[k][j].append((c, t))
                            if not gts and j == 0:
                                neg_fp[k].append(c)
                        if it == "falldown":                                   # 편 재현율도 IoU 단계 평균
                            cs = clip.setdefault(stem, {"tp": 0, "gt": 0})
                            cs["gt"] += sum(n.values()) / len(ious); cs["tp"] += sum(1 for k, c, t in sc if t and c >= cfg["at"][0]) / len(ious)
                    for k, v in n.items():
                        n_gt[k] += v
                    n_neg += not gts
            if saved is None:
                cache.parent.mkdir(parents=True, exist_ok=True); cache.write_text(json.dumps(got_all), encoding="utf-8")
            res = {"사진": len(imgs), "대상 없음 사진": n_neg, "IoU": "0.5" if len(ious) == 1 else "0.50~0.95 평균"}
            for k, nm in zip(cfg["classes"], cfg["names"]):
                res[nm] = summarize(scored[k], n_gt[k], cfg["at"])
                res[nm]["대상 없음 사진 오검"] = {f"@{x:.2f}": sum(c >= x for c in neg_fp[k]) for x in cfg["at"]}
            if clip:
                res["편별 재현율"] = {s: round(v["tp"] / max(1, v["gt"]), 3) for s, v in sorted(clip.items())}
                res["편 평균 재현율"] = round(sum(res["편별 재현율"].values()) / len(clip), 3)
            out[f"{name}|{it}" + ("|판정기추론" if judge else "")] = res
            print(name, it, json.dumps(res, ensure_ascii=False), flush=True)
    if a.out:
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    main()
