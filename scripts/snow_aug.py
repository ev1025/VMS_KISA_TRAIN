# -*- coding: utf-8 -*-
"""손라벨 방화 CCTV 프레임에 '실제 눈 영상에서 잰' 강설을 씌워 학습셋을 만든다. 라벨은 그대로(작게 모드만 좌표 변환).

왜 (2026-09-26)
    눈 편 두 편(216 주간 눈 · 272 야간 눈)을 겨냥한 눈 배경 붙여넣기(fire_snowbg_*)는 효과가 약했다.
      - 흑백불 붙여넣기: 272 불 신뢰도 0.75 -> 0.90 (이미 잡던 편), 216 최고 0.29 -> 0.42 (문턱 0.40·3회 못 넘음)
      - 작은불 붙여넣기: 216 에서 헛불. 공개셋 설경 6~10배: 점수 하락
    안개는 '손라벨 불 프레임 + 실제 안개에서 잰 물리량' 합성(fog_aug.py)이 195 를 잡았다. 같은 방식을 눈에 쓴다.
    붙여넣기는 배경만 눈이고 불은 맑은 날 불이다. 이쪽은 불까지 눈 속에 있다(눈송이가 불을 가리고 화면 대비가 준다).

무엇을 재나 (--stats, 읽기만)
    실제 눈 영상(KISA_악천후_사람 주간 눈 4편 · 야간 눈 3편)에서
      장면  밝기 V 평균 · 채도 S 평균 · 대비(V 표준편차)
      눈송이  연속 프레임 차이에서 '밝아진 작은 덩어리' = 떨어지는 눈. 프레임당 개수 · 넓이 · 세로 길이
    채점 216·272 는 같은 값을 비교로만 잰다(학습·튜닝에 안 씀. 화소는 가져오지 않는다)

합성 (한 프레임)
    1 장면 톤  주간: 채도 x0.45~0.85 · 대비 x0.70~0.95 · 옅은 산란(t 0.80~0.95) · 약간 푸른 기  / 야간: 밝히지 않음, 60% 흑백(IR)
    2 쌓인 눈  주간 50%: 화면 아래쪽의 평평하고 채도 낮은 곳을 흰색 쪽으로(불 상자 주변은 제외)
    3 눈송이  실제 눈 영상에서 뽑은 '눈 층'(프레임 - 시간 중앙값 배경, 150px 넘는 덩어리=사람·차 제거)을 screen 으로 얹는다.
              주간 층은 주간 눈 4편, 야간 층은 야간 눈 3편에서. 층이 없으면 인공 눈송이(깊이별 크기·흐림)로 대신한다
              (웹 조사 2026-09-26: 합성 입자 마스크는 실제 눈으로 일반화가 약하다. Snow100K·CSD 계열 한계)
    4 CCTV    잡음 σ 1~4 · JPEG 품질 55~85
    작게 모드(--small): 화면을 0.45~0.75 배로 줄여 가운데 두고 둘레는 흐린 가장자리로 채운다 -> 불이 216 처럼 작아진다

산출  data/학습데이터/<이름>/{images,labels}/train · train.txt · data.yaml · meta.json · params.json
      양성: 옅은 눈·짙은 눈 2벌(+ 작게 1벌) · 배경(하드네거): 1벌 (눈송이를 불로 보지 않게)
사용
    python scripts/snow_aug.py --stats
    python scripts/snow_aug.py --probe /NHNHOME/snow_probe --src handset_fire_all_20260926 --n 12
    python scripts/snow_aug.py --src handset_fire_all_20260926 --name fire_snowaug_20260926 --small
"""
import argparse
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
TD = V / "data/학습데이터"
SNOW_DIR = V / "data/원본데이터/KISA_악천후_사람/영상"
DAY_SNOW = ["C00_230_0001", "C00_235_0001", "C00_244_0001", "fall_C00_217_0004"]
NIGHT_SNOW = ["C00_221_0001", "C00_230_0002", "fall_C00_235_0002"]
EVAL_DIR = V / "data/원본데이터/kisa_배포_검증영상/deploy_val/방화(10개)/배포"
EVAL_SNOW = ["C00_216_0003", "C00_272_0003"]          # 비교로만 잰다

# --stats 실측 (2026-09-26, dumps/snow_stats_20260926.json)
#   주간 눈 4편: V 0.54~0.58 · 채도 0.025~0.10 · 대비 0.11~0.23 · 눈송이 160~2,600개/프레임 · 넓이 1~6px · 높이 1~3px(점)
#   야간 눈 3편: V 0.35~0.40 · 채도 0(흑백 IR) · 대비 0.10~0.11 · 눈송이 ~150개 · 넓이 5~75px · 높이 3~16px(조명 받은 덩어리)
#   채점 216: V 0.53 · 채도 0.063 · 대비 0.163 · 190개 · 1~2px   /  채점 272: V 0.39 · 채도 0 · 대비 0.114 · 170개 · 2~7px
#   맑은 손라벨 CCTV: 채도 ~0.17 (fog_stats) -> 주간 눈은 채도를 0.2~0.6 배로 크게 낮춘다
LEVELS = {"light": dict(n=(150, 600), op=(0.35, 0.75), alpha=(0.5, 0.8)),     # alpha = 실제 눈 층 세기
          "heavy": dict(n=(600, 2200), op=(0.5, 0.95), alpha=(0.8, 1.2))}
LAYER_DIR = TD / "_눈층_20260926"                   # 실제 눈 층 캐시(주간_*.png · 야간_*.png, 1280x720 흑백)
_LAYERS = {}


# ------------------------------------------------------------------ 재기
def clip_stats(mp4, n_pairs=40, head_skip=5.0):
    cap = cv2.VideoCapture(str(mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total < 10:
        return None
    idx = np.linspace(int(head_skip * fps), total - 3, n_pairs).astype(int)
    V_, S_, C_, cnt, area, hgt, elong = [], [], [], [], [], [], []
    for f in idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(f))
        ok1, a = cap.read(); ok2, b = cap.read()
        if not (ok1 and ok2):
            continue
        sc = 1280.0 / a.shape[1]
        if abs(sc - 1) > 0.01:
            a = cv2.resize(a, None, fx=sc, fy=sc); b = cv2.resize(b, None, fx=sc, fy=sc)
        hsv = cv2.cvtColor(b, cv2.COLOR_BGR2HSV)
        V_.append(hsv[..., 2].mean() / 255); S_.append(hsv[..., 1].mean() / 255); C_.append(hsv[..., 2].std() / 255)
        ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.int16); gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.int16)
        m = ((gb - ga) > 18).astype(np.uint8)                        # 새로 밝아진 곳 = 이 순간 지나가는 눈송이
        n, _, st, _ = cv2.connectedComponentsWithStats(m, 8)
        keep = [s for s in st[1:] if 1 <= s[cv2.CC_STAT_AREA] <= 150]   # 큰 덩어리(사람·차)는 뺀다
        cnt.append(len(keep))
        area += [int(s[cv2.CC_STAT_AREA]) for s in keep]
        hgt += [int(s[cv2.CC_STAT_HEIGHT]) for s in keep]
        elong += [s[cv2.CC_STAT_HEIGHT] / max(1, s[cv2.CC_STAT_WIDTH]) for s in keep]
    cap.release()
    q = lambda x, p: float(np.percentile(x, p)) if len(x) else 0.0
    return dict(V=round(float(np.mean(V_)), 3), S=round(float(np.mean(S_)), 3), contrast=round(float(np.mean(C_)), 3),
                flakes_per_frame=(round(q(cnt, 25)), round(q(cnt, 50)), round(q(cnt, 75))),
                flake_area_px=(q(area, 50), q(area, 90)), flake_h_px=(q(hgt, 50), q(hgt, 90)), elong_med=round(q(elong, 50), 2))


def stats():
    out = {}
    for group, clips, d in (("주간 눈", DAY_SNOW, SNOW_DIR), ("야간 눈", NIGHT_SNOW, SNOW_DIR), ("채점(비교만)", EVAL_SNOW, EVAL_DIR)):
        for c in clips:
            p = d / (c + ".mp4")
            r = clip_stats(p) if p.is_file() else None
            out[c] = dict(group=group, **(r or {"없음": str(p)}))
            print("%-8s %-18s %s" % (group, c, json.dumps(out[c], ensure_ascii=False)), flush=True)
    return out


def extract_layers(per_clip=60, tau=12, max_blob=150):
    """실제 눈 영상에서 눈 층을 뽑아 캐시한다. 층 = clip(프레임 - 시간 중앙값 배경 - tau), 큰 덩어리(사람·차) 제거."""
    LAYER_DIR.mkdir(parents=True, exist_ok=True)
    n_all = 0
    for group, clips in (("주간", DAY_SNOW), ("야간", NIGHT_SNOW)):
        for c in clips:
            cap = cv2.VideoCapture(str(SNOW_DIR / (c + ".mp4")))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0; total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total < 100:
                continue
            got = 0
            for k, start in enumerate(np.linspace(int(5 * fps), total - int(12 * fps), max(1, per_clip // 6)).astype(int)):
                # 10초 구간의 중앙값 = 그 구간 배경(눈은 시간 고주파라 중앙값에서 빠진다)
                frames = []
                for f in np.linspace(start, start + int(10 * fps), 31).astype(int):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, int(f)); ok, fr = cap.read()
                    if ok:
                        frames.append(cv2.resize(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), (1280, 720)))
                if len(frames) < 15:
                    continue
                B = np.median(np.stack(frames), axis=0).astype(np.int16)
                for fr in frames[::5]:
                    Sl = np.clip(fr.astype(np.int16) - B - tau, 0, 255).astype(np.uint8)
                    n, lab, st, _ = cv2.connectedComponentsWithStats((Sl > 0).astype(np.uint8), 8)
                    big = np.where(st[:, cv2.CC_STAT_AREA] > max_blob)[0]
                    big = big[big > 0]
                    if len(big):
                        Sl[np.isin(lab, big)] = 0
                    Sl = np.clip(Sl.astype(np.float32) * 2.0, 0, 255).astype(np.uint8)   # 차이값은 눈 밝기보다 작다. 2배로 되돌린다
                    cv2.imwrite(str(LAYER_DIR / ("%s_%s_%03d.png" % (group, c, got))), Sl); got += 1
            cap.release(); n_all += got
            print("  눈 층 %s %s %d장" % (group, c, got), flush=True)
    print("눈 층 합계 %d장 → %s" % (n_all, LAYER_DIR))


def layer(group, h, w, rnd):
    """캐시에서 눈 층 하나(0~1 float, h x w). 좌우 뒤집기·자르기. 없으면 None."""
    if group not in _LAYERS:
        _LAYERS[group] = sorted(LAYER_DIR.glob(group + "_*.png")) if LAYER_DIR.is_dir() else []
    fs = _LAYERS[group]
    if not fs:
        return None
    L = cv2.imread(str(rnd.choice(fs)), cv2.IMREAD_GRAYSCALE)
    if rnd.random() < 0.5:
        L = L[:, ::-1]
    s = rnd.uniform(0.8, 1.0)                                       # 약간 확대해 자른다(같은 층이 똑같이 반복되지 않게)
    ch, cw = int(L.shape[0] * s), int(L.shape[1] * s)
    y0, x0 = rnd.randint(0, L.shape[0] - ch), rnd.randint(0, L.shape[1] - cw)
    return cv2.resize(np.ascontiguousarray(L[y0:y0 + ch, x0:x0 + cw]), (w, h)).astype(np.float32) / 255.0


def img_stats(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return hsv[..., 2].mean() / 255, hsv[..., 1].mean() / 255, hsv[..., 2].std() / 255


# ------------------------------------------------------------------ 합성
def flakes(h, w, level, night, rnd, scale):
    """눈송이 층(알파 0~1, float32). 깊이 z(0=가깝다) 로 크기·흐림·길이·밝기를 정한다."""
    p = LEVELS[level]
    n = int(rnd.uniform(*p["n"]) * (h * w) / (1280 * 720))
    ang = np.deg2rad(rnd.uniform(-25, 25))                        # 바람. 0 = 수직 낙하
    far = np.zeros((h, w), np.float32); near = np.zeros((h, w), np.float32)
    for _ in range(n):
        z = rnd.random() ** 0.7                                    # 먼 눈이 더 많다
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        r = max(1, int(round(((2.0 + 6.0 * (1 - z) ** 2) if night else (0.6 + 1.6 * (1 - z) ** 2)) * scale)))
        L = ((1.0 + 6.0 * (1 - z)) if night else (0.5 + 2.5 * (1 - z) ** 1.5)) * scale   # 실측: 주간 1~3px 점 · 야간 3~16px
        dx, dy = np.sin(ang) * L, np.cos(ang) * L
        a = rnd.uniform(*p["op"]) * (0.45 + 0.55 * (1 - z))
        if night:
            a *= 1.0 if z < 0.35 else 0.55                         # 야간: 조명 가까운 눈만 밝게 보인다
        layer = near if z < 0.3 else far
        cv2.line(layer, (int(x), int(y)), (int(x + dx), int(y + dy)), float(a), thickness=r, lineType=cv2.LINE_AA)
    far = cv2.GaussianBlur(far, (0, 0), 0.6 * scale + 0.3)
    near = cv2.GaussianBlur(near, (0, 0), 1.6 * scale + 0.5)       # 가까운 눈은 초점이 안 맞는다
    return np.clip(far + near, 0, 1)


def boxes_px(lab_txt, w, h):
    out = []
    for ln in lab_txt.strip().splitlines():
        p = ln.split()
        if len(p) >= 5:
            c, x, y, bw, bh = int(p[0]), *map(float, p[1:5])
            out.append((c, (x - bw / 2) * w, (y - bh / 2) * h, (x + bw / 2) * w, (y + bh / 2) * h))
    return out


def snow(img, lab_txt, level, rnd, small=False):
    h, w = img.shape[:2]
    prm = dict(level=level)
    labels = lab_txt
    if small:                                                      # 화면 축소 -> 불이 작아진다(216 불 25x12px)
        s = rnd.uniform(0.45, 0.75)
        nw, nh = int(w * s), int(h * s)
        ox, oy = rnd.randint(0, w - nw), rnd.randint(0, h - nh)
        # 가장자리 채움: 불 자리를 그 프레임 중앙값 색으로 먼저 지우고 크게 흐린다(라벨 없는 흐린 불 복사본이 생기지 않게. 표본 확인 2026-09-26)
        base = img.copy(); med = np.median(img.reshape(-1, 3), axis=0).astype(np.uint8)
        for _, x1, y1, x2, y2 in boxes_px(lab_txt, w, h):
            pw, ph = (x2 - x1) * 0.6 + 6, (y2 - y1) * 0.6 + 6
            base[max(0, int(y1 - ph)):int(y2 + ph), max(0, int(x1 - pw)):int(x2 + pw)] = med
        bg = cv2.GaussianBlur(cv2.resize(base, (w // 16, h // 16), interpolation=cv2.INTER_AREA), (0, 0), 1.5)
        canvas = cv2.resize(bg, (w, h), interpolation=cv2.INTER_CUBIC)
        canvas[oy:oy + nh, ox:ox + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        img = canvas
        new = []
        for ln in lab_txt.strip().splitlines():
            p = ln.split()
            if len(p) >= 5:
                c, x, y, bw, bh = int(p[0]), *map(float, p[1:5])
                new.append("%d %.6f %.6f %.6f %.6f" % (c, (ox + x * nw) / w, (oy + y * nh) / h, bw * s, bh * s))
        labels = "\n".join(new) + ("\n" if new else "")
        prm.update(small=round(s, 3))
    gray_mean = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()) / 255.0
    night = gray_mean < 0.22
    f = img.astype(np.float32) / 255.0
    if night:
        if rnd.random() < 0.85:                                     # 야간 IR 흑백 (야간 눈 3편·272 모두 채도 0)
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
            f = np.repeat(g[..., None], 3, axis=2); prm["ir"] = 1
    else:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
        sat = rnd.uniform(0.2, 0.6); hsv[..., 1] *= sat              # 실측 채도 0.03~0.10 (맑은 날 0.17)
        f = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32) / 255.0
        c = rnd.uniform(0.65, 0.95); m = f.mean()
        f = m + (f - m) * c                                         # 대비가 준다
        t = rnd.uniform(0.80, 0.95); A = rnd.uniform(0.80, 0.95)
        f = f * t + A * (1 - t)                                     # 옅은 산란(눈 오는 날 공기)
        f[..., 0] += rnd.uniform(0.0, 0.03)                         # 약간 푸른 기(BGR 의 B)
        prm.update(sat=round(sat, 2), contrast=round(c, 2), t=round(t, 2))
        if rnd.random() < 0.5:                                      # 쌓인 눈: 아래쪽의 평평하고 색 옅은 곳
            gy = cv2.Sobel(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_32F, 0, 1, ksize=3)
            gx = cv2.Sobel(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_32F, 1, 0, ksize=3)
            flat = (np.sqrt(gx ** 2 + gy ** 2) < 25).astype(np.float32)
            low_s = (cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1] < 70).astype(np.float32)
            horizon = rnd.uniform(0.35, 0.6)
            yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
            m_ = flat * low_s * np.clip((yy - horizon) * 4, 0, 1)
            for _, x1, y1, x2, y2 in boxes_px(labels, w, h):         # 불 상자와 둘레는 덮지 않는다
                pw, ph = (x2 - x1) * 0.4 + 4, (y2 - y1) * 0.4 + 4
                m_[max(0, int(y1 - ph)):int(y2 + ph), max(0, int(x1 - pw)):int(x2 + pw)] = 0
            m_ = cv2.GaussianBlur(m_, (0, 0), 9) * rnd.uniform(0.3, 0.7)
            f = f * (1 - m_[..., None]) + 0.93 * m_[..., None]
            prm["cover"] = 1
    L = layer("야간" if night else "주간", h, w, rnd)
    if L is not None:                                               # 실제 눈 층: screen 합성 1-(1-I)(1-aS)
        al = rnd.uniform(*LEVELS[level]["alpha"])
        f = 1 - (1 - np.clip(f, 0, 1)) * (1 - np.clip(al * L, 0, 1)[..., None])
        prm.update(layer=1, alpha=round(al, 2))
    else:
        a = flakes(h, w, level, night, rnd, scale=w / 1280.0)
        white = 1.0 if not night else rnd.uniform(0.75, 1.0)
        f = f * (1 - a[..., None]) + white * a[..., None]
    f += np.random.default_rng(rnd.randrange(1 << 30)).normal(0, rnd.uniform(1, 4) / 255.0, f.shape).astype(np.float32)
    out = (np.clip(f, 0, 1) * 255).astype(np.uint8)
    q = rnd.randint(55, 85)
    out = cv2.imdecode(cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
    prm.update(night=int(night), jpeg=q)
    return out, labels, prm


def label_of(img_path):
    lp = Path(str(img_path).replace("/images/", "/labels/")).with_suffix(".txt")
    return lp if lp.is_file() else None


def variants(positive, small, only_small=False):
    if only_small:                                                  # 작게만: 양성마다 짙은 눈+축소 1벌, 배경은 안 만든다
        return [("heavy", True)] if positive else []
    if not positive:
        return [("light", False)] if random.random() < 0.5 else [("heavy", False)]
    v = [("light", False), ("heavy", False)]
    return v + [("heavy", True)] if small else v


def build(src, name, rnd, small, only_small=False):
    lines = [l.strip() for l in open(TD / src / "train.txt", encoding="utf-8") if l.strip()]
    out = TD / name
    assert not out.exists(), "이미 있음: %s" % out
    (out / "images/train").mkdir(parents=True); (out / "labels/train").mkdir(parents=True)
    made, log, t0, n_pos, n_neg = [], {}, time.time(), 0, 0
    random.seed(rnd.random())
    for i, src_img in enumerate(lines):
        img = cv2.imread(src_img); lp = label_of(src_img)
        if img is None or lp is None:
            continue
        lab = lp.read_text(encoding="utf-8")
        positive = bool(lab.strip()); n_pos += positive; n_neg += not positive
        for lv, sm in variants(positive, small, only_small):
            im2, lab2, prm = snow(img, lab, lv, rnd, small=sm)
            stem = Path(src_img).stem + "_snow" + lv[0] + ("s" if sm else "")
            dst = out / "images/train" / (stem + ".jpg")
            cv2.imwrite(str(dst), im2, [cv2.IMWRITE_JPEG_QUALITY, 95])
            (out / "labels/train" / (stem + ".txt")).write_text(lab2, encoding="utf-8")
            made.append(str(dst)); log[stem] = dict(src=src_img, **prm)
        if (i + 1) % 500 == 0:
            print("  %d/%d  (%.0f초)" % (i + 1, len(lines), time.time() - t0), flush=True)
    (out / "train.txt").write_text("\n".join(made) + "\n", encoding="utf-8")
    (out / "data.yaml").write_text("path: %s\ntrain: %s\nval: %s\nnc: 2\nnames: ['fire', 'smoke']\n"
                                   % (out, out / "train.txt", out / "train.txt"), encoding="utf-8")
    meta = dict(name=name, mode="fire", built=time.strftime("%Y-%m-%d %H:%M:%S"), source=src,
                what="손라벨 방화 프레임에 실제 눈 영상에서 잰 강설 합성(장면 톤·쌓인 눈·눈송이·CCTV 잡음). 라벨은 원본(작게 모드만 좌표 변환)",
                levels=LEVELS, small=small, only_small=only_small, n_source=len(lines), n_source_pos=n_pos, n_source_neg=n_neg, n_out=len(made),
                params_of_each="params.json", measured_from="scripts/snow_aug.py --stats (KISA_악천후_사람 눈 7편. 채점 216·272 는 비교만)")
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "params.json").write_text(json.dumps(log, ensure_ascii=False), encoding="utf-8")
    print("완료 %s: 원본 %d(양성 %d·배경 %d) → %d장 (%.0f초)" % (name, len(lines), n_pos, n_neg, len(made), time.time() - t0))


def probe(src, out_dir, n, rnd):
    """검증 표본: 원본 · 옅은 · 짙은 · 작게 4벌과 톤 수치."""
    lines = [l.strip() for l in open(TD / src / "train.txt", encoding="utf-8") if l.strip()]
    pos = [l for l in lines if label_of(l) and label_of(l).read_text().strip()]
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rows = []
    for src_img in rnd.sample(pos, min(n, len(pos))):
        img = cv2.imread(src_img); lab = label_of(src_img).read_text(); stem = Path(src_img).stem
        cv2.imwrite(str(out / (stem + "_0orig.jpg")), img)
        rows.append((stem, "orig") + tuple(round(v, 3) for v in img_stats(img)))
        for lv, sm in (("light", False), ("heavy", False), ("heavy", True)):
            im2, lab2, prm = snow(img, lab, lv, rnd, small=sm)
            tag = lv + ("_small" if sm else "")
            cv2.imwrite(str(out / ("%s_%s.jpg" % (stem, tag))), im2)
            (out / ("%s_%s.txt" % (stem, tag))).write_text(lab2)
            rows.append((stem, tag) + tuple(round(v, 3) for v in img_stats(im2)))
    for r in rows:
        print("%-28s %-12s V %.3f S %.3f 대비 %.3f" % r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--layers", action="store_true", help="실제 눈 영상에서 눈 층을 뽑아 캐시")
    ap.add_argument("--src", default="handset_fire_all_20260926")
    ap.add_argument("--name", default="fire_snowaug_20260926")
    ap.add_argument("--small", action="store_true", help="양성마다 화면 축소(불 작게) 1벌 더")
    ap.add_argument("--only-small", action="store_true", help="축소 벌만 만든다(따로 실험하려고)")
    ap.add_argument("--probe", default=None)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    if a.layers:
        extract_layers()
    elif a.stats:
        json.dump(stats(), open(V / "dumps/snow_stats_20260926.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    elif a.probe:
        probe(a.src, a.probe, a.n, rnd)
    else:
        build(a.src, a.name, rnd, a.small, a.only_small)


if __name__ == "__main__":
    main()
