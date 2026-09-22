# -*- coding: utf-8 -*-
"""SAM 전파 폴리곤으로 사람을 잘라 작게 줄여서 CCTV 배경 프레임에 붙인다(copy-paste). 라벨은 붙인 자리에 새로 쓴다.

왜 (2026-09-19)
    침입·배회 실패 편의 절반이 화면 높이 5%(34~50px) 사람이다. 손라벨은 큰 사람 위주라 그 크기가 거의 없다.
    09-16 의 눈·비 오버레이 합성은 '실패 열화(소형·가림)' 와 달라 폐기됐다. 이번은 실패 열화 그 자체(작게 보이는 사람)를 만든다.

재료
    사람 조각   data/학습데이터/자동라벨/sam2/*.json 의 polys (전파 마스크 폴리곤, 190편 10,654프레임). 채점셋(C00_*) 편은 뺀다.
    배경       person_mask_hn_20260918 의 학습 프레임(연구개발 CCTV, 라벨 있음). 기존 라벨과 겹치지 않는 자리에만 붙인다.

어떻게
    조각은 원본에서 높이 90px 이상인 것만 골라(줄여도 형태가 남게) 28~60px 로 줄인다(INTER_AREA + 약한 블러).
    배경의 위쪽 15~60% 구간(먼 곳)에 1~3명. 배경이 흑백(야간 적외선)이면 조각도 흑백으로. 밝기는 배경 자리에 반쯤 맞춘다.
    가장자리는 알파 마스크를 1px 흐려 붙인다. 붙인 박스는 알파 마스크의 외접 사각형.

산출  data/학습데이터/<이름>/{images,labels}/train · train.txt · data.yaml · meta.json · /tmp/paste_preview/ (눈으로 볼 견본)

사용
    python scripts/person_paste.py --name person_mask_hn_paste_20260919 --n-out 5000
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]

TD = V / "data/학습데이터"
SAM = TD / "자동라벨/sam2"


_MP4 = None


def find_video(stem):
    """연구개발·AI허브 원본에서 클립 mp4 를 찾는다. KP.find_mp4 는 채점셋(deploy_val)만 보므로 여기서는 쓰지 않는다."""
    global _MP4
    if _MP4 is None:
        _MP4 = {}
        for root in ("kisa_연구개발_사람영상", "aihub_침입쓰러짐영상", "aihub171_이상행동"):
            for p in (V / "data/원본데이터" / root).rglob("*.mp4"):
                _MP4.setdefault(p.stem, p)
    return _MP4.get(stem)


def cutouts(max_n, rnd, min_h=90):
    """(BGR 조각, 알파 0~1, 출처) 목록. 편마다 폴리곤 프레임을 골고루 뽑는다."""
    out = []
    files = sorted(p for p in SAM.glob("*.json") if not p.stem.startswith("C00_"))     # 채점셋 제외
    rnd.shuffle(files)
    per_clip = max(3, max_n // max(1, len(files)) + 1)
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        polys = d.get("polys") or {}
        if not polys:
            continue
        mp4 = find_video(d.get("clip", f.stem))
        if mp4 is None:
            continue
        cap = cv2.VideoCapture(str(mp4)); fps = cap.get(cv2.CAP_PROP_FPS) or 30
        keys = sorted(polys, key=float)
        picks = keys if len(keys) <= per_clip else [keys[i] for i in sorted(rnd.sample(range(len(keys)), per_clip))]
        for t in picks:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(float(t) * fps))); ok, fr = cap.read()
            if not ok:
                continue
            H, W = fr.shape[:2]
            for oid, pts in polys[t].items():
                if not pts or len(pts) < 3:
                    continue
                P = np.array([[x * W, y * H] for x, y in pts], dtype=np.int32)
                x1, y1 = P.min(axis=0); x2, y2 = P.max(axis=0)
                if y2 - y1 < min_h or x2 - x1 < 12:
                    continue
                m = np.zeros((H, W), np.uint8); cv2.fillPoly(m, [P], 255)
                x1, y1 = max(0, x1 - 2), max(0, y1 - 2); x2, y2 = min(W, x2 + 3), min(H, y2 + 3)
                out.append((fr[y1:y2, x1:x2].copy(), (m[y1:y2, x1:x2] / 255.0).astype(np.float32), "%s@%s#%s" % (d.get("clip", f.stem), t, oid)))
                if len(out) >= max_n:
                    cap.release(); return out
        cap.release()
    return out


def read_labels(lp):
    rows = []
    if lp.is_file():
        for ln in lp.read_text(encoding="utf-8").splitlines():
            p = ln.split()
            if len(p) >= 5:
                rows.append([float(x) for x in p[1:5]])
    return rows


def overlaps(box, others, W, H):
    x, y, w, h = box
    ax1, ay1, ax2, ay2 = (x - w / 2) * W, (y - h / 2) * H, (x + w / 2) * W, (y + h / 2) * H
    for ox, oy, ow, oh in others:
        bx1, by1, bx2, by2 = (ox - ow / 2) * W, (oy - oh / 2) * H, (ox + ow / 2) * W, (oy + oh / 2) * H
        if min(ax2, bx2) - max(ax1, bx1) > 0 and min(ay2, by2) - max(ay1, by1) > 0:
            return True
    return False


def paste_one(bg, fg, alpha, rnd, gray_bg):
    """조각 하나를 배경의 위쪽 먼 구역에 붙인다. 성공하면 (배경, 정규화 박스), 실패하면 None."""
    H, W = bg.shape[:2]
    th = rnd.randint(28, 60)
    s = th / fg.shape[0]
    tw = max(6, int(round(fg.shape[1] * s)))
    f = cv2.resize(fg, (tw, th), interpolation=cv2.INTER_AREA).astype(np.float32)
    a = cv2.resize(alpha, (tw, th), interpolation=cv2.INTER_AREA)
    a = cv2.GaussianBlur(a, (0, 0), 0.8)[..., None]
    f = cv2.GaussianBlur(f, (0, 0), rnd.uniform(0.3, 0.7))
    if gray_bg:
        g = cv2.cvtColor(f.astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32)
        f = np.repeat(g[..., None], 3, axis=2)
    for _ in range(20):
        x0 = rnd.randint(0, max(0, W - tw - 1)); y0 = rnd.randint(int(0.15 * H), int(0.60 * H))
        if y0 + th >= H:
            continue
        roi = bg[y0:y0 + th, x0:x0 + tw].astype(np.float32)
        m_bg = roi.mean(); m_fg = (f * a).sum() / max(1e-3, a.sum() * 3)
        k = (m_bg / max(1e-3, m_fg)) ** 0.5                       # 밝기를 배경 자리에 반쯤 맞춘다
        ff = np.clip(f * k, 0, 255)
        bg[y0:y0 + th, x0:x0 + tw] = (roi * (1 - a) + ff * a).astype(np.uint8)
        ys, xs = np.where(a[..., 0] > 0.3)
        if len(xs) == 0:
            return None
        bx1, bx2, by1, by2 = x0 + xs.min(), x0 + xs.max() + 1, y0 + ys.min(), y0 + ys.max() + 1
        return bg, [((bx1 + bx2) / 2) / W, ((by1 + by2) / 2) / H, (bx2 - bx1) / W, (by2 - by1) / H]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="person_mask_hn_paste_20260919")
    ap.add_argument("--bg", default="person_mask_hn_20260918")
    ap.add_argument("--n-out", type=int, default=5000)
    ap.add_argument("--n-cut", type=int, default=2500)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    t0 = time.time()
    cuts = cutouts(a.n_cut, rnd)
    print("사람 조각 %d개 (%.0f초)" % (len(cuts), time.time() - t0), flush=True)
    if len(cuts) < 50:
        sys.exit("조각이 너무 적다")
    bgs = [l.strip() for l in open(TD / a.bg / "train.txt", encoding="utf-8") if l.strip()]
    rnd.shuffle(bgs)
    out = TD / a.name
    (out / "images/train").mkdir(parents=True, exist_ok=True); (out / "labels/train").mkdir(parents=True, exist_ok=True)
    prev = Path("/tmp/paste_preview"); prev.mkdir(exist_ok=True)
    made, n_paste, sizes = [], 0, []
    for i, bp in enumerate(bgs):
        if len(made) >= a.n_out:
            break
        bg = cv2.imread(bp)
        if bg is None:
            continue
        H, W = bg.shape[:2]
        lp = Path(bp.replace("/images/", "/labels/")).with_suffix(".txt")
        labels = read_labels(lp)
        gray_bg = bool(np.abs(bg[..., 0].astype(int) - bg[..., 2].astype(int)).mean() < 2.0)   # 야간 적외선 = 채널 차 거의 0
        new = []
        for _ in range(rnd.choice([1, 2, 2, 3])):
            fg, al, _src = rnd.choice(cuts)
            r = paste_one(bg, fg, al, rnd, gray_bg)
            if r is None:
                continue
            bg, box = r
            if overlaps(box, labels + new, W, H):
                bg = cv2.imread(bp)                                   # 겹치면 이 배경은 처음부터 다시
                for bx in new:                                        # (이미 붙인 것도 버린다)
                    pass
                new = []; break
            new.append(box); sizes.append(box[3] * H)
        if not new:
            continue
        stem = Path(bp).stem + "_paste"
        cv2.imwrite(str(out / "images/train" / (stem + ".jpg")), bg, [cv2.IMWRITE_JPEG_QUALITY, 92])
        rows = ["0 %.6f %.6f %.6f %.6f" % tuple(b) for b in labels + new]
        (out / "labels/train" / (stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
        made.append(str(out / "images/train" / (stem + ".jpg"))); n_paste += len(new)
        if len(made) <= 12:                                            # 견본: 붙인 박스만 그려 둔다
            pv = bg.copy()
            for cx, cy, w, h in new:
                cv2.rectangle(pv, (int((cx - w / 2) * W), int((cy - h / 2) * H)), (int((cx + w / 2) * W), int((cy + h / 2) * H)), (0, 255, 0), 1)
            cv2.imwrite(str(prev / (stem + ".jpg")), pv)
        if len(made) % 1000 == 0:
            print("  %d장 (%.0f초)" % (len(made), time.time() - t0), flush=True)
    (out / "train.txt").write_text("\n".join(made) + "\n", encoding="utf-8")
    (out / "data.yaml").write_text("path: %s\ntrain: %s\nval: %s\nnc: 1\nnames: ['person']\n" % (out, out / "train.txt", out / "train.txt"), encoding="utf-8")
    sizes.sort()
    meta = dict(name=a.name, mode="person", built=time.strftime("%Y-%m-%d %H:%M:%S"), background=a.bg,
                what="SAM 전파 폴리곤 사람 조각을 28~60px 로 줄여 CCTV 배경 위쪽(먼 곳)에 붙임. 채점셋 편 조각 제외",
                n_cutouts=len(cuts), n_out=len(made), n_pasted=n_paste,
                pasted_height_px=dict(p10=sizes[len(sizes) // 10], p50=sizes[len(sizes) // 2], p90=sizes[9 * len(sizes) // 10]) if sizes else None,
                why="침입·배회 실패 편의 절반이 34~50px 사람(2026-09-19 fail_report). 손라벨에 그 크기가 거의 없다")
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("완료 %s: %d장 · 붙인 사람 %d명 · 높이 중앙 %.0fpx (%.0f초) · 견본 %s" % (a.name, len(made), n_paste, sizes[len(sizes) // 2] if sizes else 0, time.time() - t0, prev))


if __name__ == "__main__":
    main()
