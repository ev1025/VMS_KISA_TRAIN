# -*- coding: utf-8 -*-
"""눈·안개 CCTV 배경에 실제 불꽃을 합성해 방화 학습셋을 만든다.

왜 (2026-09-23, 사용자 지시)
    채점 10편 중 못 잡는 편이 216(주간 눈)·272(야간 눈) 다. 그런데 학습에 쓸 수 있는
    연구개발 방화 75편에 눈·비·안개가 0편이다. 눈 자료는 FASDD 웹이미지 3,579장뿐이고
    그것은 CCTV 화면이 아니다. 배경만 있으면 되는 상황이라 배경을 가져와 불을 얹는다.

    배경 9편은 KISA_악천후_사람(사람 항목 영상)이라 불이 안 난다. 방화 학습에 쓴 적도 없다.
    눈 5 · 안개 2 · 야간비 2.

불꽃 모양은 추측하지 않는다 (앞선 4번의 실패에서 배운 것)
    처음에는 잘라 온 네모 안의 밝기로 알파를 만들었다. 네 번 고쳤지만 전부 실패했다.
        1차 가산 합성 -> 255 를 넘겨 흰 덩어리
        2차 screen    -> 밝은 배경에서 씻겨 사라짐
        3차 무채색    -> 아예 안 보임
        4차 밝기 목표 -> 네모난 회색 얼룩
    밝기로는 불꽃 실루엣이 안 나온다. 잘라 온 네모의 배경까지 알파가 남아 네모가 보인다.
    정확한 불꽃 마스크는 이미 있다. SAM2 전파 폴리곤(data/학습데이터/자동라벨/sam2/)에
    방화 클립 125편이 들어 있고, 객체 1 = 불 · 객체 2 = 연기로 고정돼 있다(dash_v2/js/editor.js).
    그 폴리곤을 그대로 마스크로 쓴다.

연기는 안 쓴다
    손라벨 클래스 0(불) 박스 안이 실제로는 흰 연기인 경우가 많다(48px 이상 865개 중 주황 불꽃 314개).
    연기를 얹으면 '흰 덩어리 = 불' 을 가르쳐 오경보가 는다. 객체 1(불) 만 쓰고 색으로 한 번 더 거른다.

무엇을 만드나
    images/train  배경 프레임에 불꽃 1~2개를 얹은 것 + 안 얹은 같은 배경(음성)
    labels/train  얹은 자리의 박스(클래스 0 = 불). 음성은 빈 txt
    _preview/     눈으로 확인할 견본. 학습 목록에는 안 들어간다

쓰는 법
    python scripts/fire_paste.py --name fire_snowbg_20260923 --n-out 2000
"""
import argparse
import json
import random
import sys
from pathlib import Path

import cv2
import numpy as np

V = Path(__file__).resolve().parents[1]
BG_DIR = V / "data/원본데이터/KISA_악천후_사람/영상"
FIRE_VID = V / "data/원본데이터/kisa_연구개발_방화영상"
SAM_DIR = V / "data/학습데이터/자동라벨/sam2"
FLAME_CACHE = V / "data/학습데이터/_불꽃마스크_20260923"

# 사용자가 고른 배경 9편. 눈 5 · 안개 2 · 야간비 2
BG_CLIPS = ["C00_146_0001", "C00_146_0002", "C00_188_0001", "C00_221_0001",
            "C00_230_0001", "C00_230_0002", "C00_235_0001", "C00_244_0001", "C00_294_0002"]

# 불은 눈 배경에만 얹는다 (2026-09-23 사용자 지적).
#   안개는 fire_mask_hn_fog_20260919(불 장면에 안개 합성)으로 이미 해결됐다. 195 가 전 규칙에서 정검이다.
#   비도 146(야간비)과 155(주간비) 둘 다 정검이다.
#   못 잡는 것은 216(주간 눈)과 272(야간 눈) 뿐이라 거기에만 학습 신호를 준다.
# 안개와 비 배경은 불 없음으로만 넣는다. 악천후를 불로 착각하지 않게 하는 쪽으로는 값어치가 있다.
BG_POS = ["C00_230_0001", "C00_235_0001", "C00_244_0001",   # 주간 눈
          "C00_221_0001", "C00_230_0002"]                   # 야간 눈

# 흑백(야간 적외선)으로 찍힌 방화 편. 여기서는 불이 주황 불꽃이 아니라 흰 원반이다.
# 못 잡는 채점 편 272(야간 눈)가 이 모습이라, 조각을 따로 뽑아 쓸 수 있게 이름을 박아 둔다.
흑백편 = {"C051105_001", "C051205_001", "C051305_001", "C052205_005",
          "C052305_005", "C058105_002", "C058205_002", "C058305_002"}

FIRE_OBJ = "1"          # SAM 객체 규약: 1 = 불, 2 = 연기
FIRE_CLS = 0            # names: [fire, smoke]
MIN_FLAME_PX = 22       # 이보다 작은 불꽃은 줄이면 모양이 사라진다
MAX_FILL = 0.85         # 마스크가 경계상자를 이보다 꽉 채우면 통·배경까지 물린 것이다
# 얹을 폭(px). 배경 종류마다 다르게 한다. 채점 편의 실제 불 폭이 14~19px 이다.
#   눈    작게(사용자 지시). 216 의 불이 19px 다
#   안개  195 의 불이 14px 다
#   야간  빛덩어리로 번지므로 조금 크게 잡아도 실제와 비슷하다
OUT_W_BY_BG = {
    "C00_230_0001": (10, 26), "C00_235_0001": (10, 26), "C00_244_0001": (10, 26),   # 주간 눈
    "C00_221_0001": (12, 34), "C00_230_0002": (12, 34),                             # 야간 눈
    "C00_188_0001": (12, 30), "C00_294_0002": (12, 30),                             # 안개
    "C00_146_0001": (12, 34), "C00_146_0002": (12, 34),                             # 야간 비
}
OUT_W = (10, 34)


def 불꽃인가(bgr, mask):
    """마스크 안이 주황 불꽃인지 본다. 흰 연기를 거른다."""
    m = mask > 128
    if m.sum() < 30:
        return False
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0][m].astype(np.float32)
    s = hsv[:, :, 1][m].astype(np.float32)
    빨강주황 = float(((h < 25) | (h > 160)).mean())   # OpenCV 색상환 0~179, 빨강이 양 끝
    return 빨강주황 > 0.45 and float(s.mean()) > 45


def 불꽃뽑기(n_want=1500):
    """SAM2 불 폴리곤으로 불꽃 조각(BGR + 알파)을 잘라 모은다. 한 번 뽑으면 파일로 남긴다."""
    FLAME_CACHE.mkdir(parents=True, exist_ok=True)
    있는것 = sorted(FLAME_CACHE.glob("*.png"))
    if len(있는것) >= n_want:
        print("  불꽃 조각 다시 씀 %d개" % len(있는것))
        return 있는것

    js = sorted(SAM_DIR.glob("*.json"))
    random.shuffle(js)
    뽑음 = 0
    for jp in js:
        if 뽑음 >= n_want:
            break
        try:
            d = json.loads(jp.read_text(encoding="utf-8"))
        except Exception:
            continue
        clip = d.get("clip") or jp.stem
        mp4 = FIRE_VID / (clip + ".mp4")
        if not mp4.is_file():
            continue                                   # 방화 원본이 없는 클립(사람·합성)
        polys = d.get("polys") or {}
        times = [t for t, objs in polys.items() if FIRE_OBJ in objs]
        if not times:
            continue
        random.shuffle(times)
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        for t in times:                                # 프레임마다 불꽃이 흔들려 모양이 다르다. 다 쓴다
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(float(t) * fps))
            ok, fr = cap.read()
            if not ok:
                continue
            H, W = fr.shape[:2]
            pts = np.array([[int(x * W), int(y * H)] for x, y in polys[t][FIRE_OBJ]], np.int32)
            if len(pts) < 3:
                continue
            x, y, w, h = cv2.boundingRect(pts)
            if min(w, h) < MIN_FLAME_PX:
                continue
            m = np.zeros((H, W), np.uint8)
            cv2.fillPoly(m, [pts], 255)
            crop, mcrop = fr[y:y + h, x:x + w], m[y:y + h, x:x + w]
            # 불꽃은 위로 갈수록 좁아져 경계상자를 꽉 채우지 않는다.
            # 꽉 채우면 드럼통이나 배경까지 물린 것이고, 얹으면 네모 자국이 남는다.
            if float((mcrop > 128).mean()) > MAX_FILL:
                continue
            # 흑백(야간 적외선) 편은 색으로 거를 수 없다(채도 0). 밝기만 보고 받는다.
            # 못 잡는 채점 편 272(야간 눈)가 그 모습이라 이 조각이 꼭 필요하다.
            if clip not in 흑백편 and not 불꽃인가(crop, mcrop):
                continue
            mcrop = cv2.GaussianBlur(mcrop, (0, 0), max(0.8, min(w, h) / 20.0))   # 테두리 1px 흐리기
            rgba = np.dstack([crop, mcrop])
            꼬리 = "_흑백" if clip in 흑백편 else "_컬러"
            cv2.imwrite(str(FLAME_CACHE / ("%s_%s%s.png" % (clip, t, 꼬리))), rgba)
            뽑음 += 1
            if 뽑음 % 50 == 0:
                print("  불꽃 %d개" % 뽑음, flush=True)
        cap.release()
    return sorted(FLAME_CACHE.glob("*.png"))


def 배경프레임(step_s=3.0, head_skip=10.0):
    """9편에서 일정 간격으로 프레임을 뽑는다. 앞뒤 10초는 화면이 흔들려서 버린다."""
    out = []
    for c in BG_CLIPS:
        mp4 = BG_DIR / (c + ".mp4")
        if not mp4.is_file():
            print("  배경 없음 %s" % c)
            continue
        cap = cv2.VideoCapture(str(mp4))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        step = max(1, int(round(fps * step_s)))
        got = 0
        for i in range(int(fps * head_skip), max(1, n - int(fps * head_skip)), step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, fr = cap.read()
            if ok:
                out.append((c, round(i / fps, 1), fr))
                got += 1
        cap.release()
        print("  배경 %s %d장" % (c, got), flush=True)
    return out


def 흔들기(rgba):
    """조각을 얹을 때마다 조금씩 바꾼다.

    왜: 불 폴리곤이 69편에서 나왔으므로 서로 다른 불은 69개뿐이다. 그대로 돌려 쓰면
    모델이 그 불들을 외운다. 좌우 뒤집기·약한 회전·색과 밝기 흔들기로 같은 불이
    매번 조금 다르게 보이게 한다. 불은 흔들리는 것이라 이 변형이 부자연스럽지 않다."""
    if random.random() < 0.5:
        rgba = rgba[:, ::-1]
    각도 = random.uniform(-12, 12)
    if abs(각도) > 1:
        h, w = rgba.shape[:2]
        M = cv2.getRotationMatrix2D((w / 2, h / 2), 각도, 1.0)
        rgba = cv2.warpAffine(rgba, M, (w, h), flags=cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    bgr = rgba[:, :, :3].astype(np.float32)
    hsv = cv2.cvtColor(np.clip(bgr, 0, 255).astype(np.uint8), cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 0] = (hsv[:, :, 0] + random.uniform(-6, 6)) % 180      # 붉은기~노란기 사이로만
    hsv[:, :, 1] = np.clip(hsv[:, :, 1] * random.uniform(0.85, 1.15), 0, 255)
    hsv[:, :, 2] = np.clip(hsv[:, :, 2] * random.uniform(0.85, 1.15), 0, 255)
    bgr = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)
    return np.dstack([bgr, rgba[:, :, 3]])


def 채도(im):
    """평균 채도. 0 에 가까우면 흑백이다(야간 적외선). 272 는 채도가 0 이었다."""
    return float(cv2.cvtColor(im, cv2.COLOR_BGR2HSV)[:, :, 1].mean())


def 얹기(bg, rgba, cx, cy):
    """배경에 불꽃을 얹는다. 마스크가 정확하므로 알파로 덮고 빛무리만 더한다."""
    # 빛무리가 조각 테두리에서 잘리면 네모 자국이 남는다(야간은 번짐 반지름이 커서 특히 그렇다).
    # 알파 0 인 여백을 둘러 두면 번짐이 여백 안에서 자연스럽게 0 으로 사라진다.
    여백 = max(6, int(max(rgba.shape[:2]) * 0.8))
    rgba = cv2.copyMakeBorder(rgba, 여백, 여백, 여백, 여백, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    H, W = bg.shape[:2]
    ph, pw = rgba.shape[:2]
    x0, y0 = int(cx - pw / 2), int(cy - ph / 2)
    x1, y1 = x0 + pw, y0 + ph
    sx0, sy0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    hh, ww = y1 - y0, x1 - x0
    if hh < 6 or ww < 6:
        return None
    p = rgba[sy0:sy0 + hh, sx0:sx0 + ww, :3].astype(np.float32)
    a = rgba[sy0:sy0 + hh, sx0:sx0 + ww, 3].astype(np.float32) / 255.0
    if a.max() < 0.5:
        return None
    roi = bg[y0:y1, x0:x1].astype(np.float32)
    배경밝기 = float(roi.mean())

    # 배경이 흑백이면(야간 적외선) 불도 흑백으로 찍힌다. 272 는 채도가 0 이었다.
    흑백배경 = 채도(bg) < 15
    어두움 = float(roi.mean()) < 90
    if 흑백배경:
        g = cv2.cvtColor(np.clip(p, 0, 255).astype(np.uint8), cv2.COLOR_BGR2GRAY)
        p = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR).astype(np.float32)

    # 불꽃 몸통의 밝기를 장면에 맞게 맞춘다. 원본이 어둡게 찍혔어도 광원으로 보이게.
    # 야간은 카메라가 어두운 장면에 노출을 맞춰 불이 하얗게 타버린다. 거의 255 까지 올린다.
    핵 = a > 0.6
    if 핵.sum() >= 4:
        현재 = float(p[핵].max())
        if 현재 > 8:
            목표 = random.uniform(245, 255) if 어두움 else random.uniform(215, 250)
            p = np.clip(p * (목표 / 현재), 0, 255)

    aa = a[..., None]
    out = roi * (1 - aa) + p * aa
    # 빛무리. 반드시 '마스크를 씌운 빛' 을 흐려야 한다. 조각 원본을 그대로 흐리면
    # 마스크 밖 배경까지 칠해져 네모난 밝은 테두리가 남는다(2026-09-23 미리보기의 흠).
    # 야간은 실제로 불꽃 모양이 사라지고 빛덩어리만 남으므로 크게·세게 번지게 한다.
    빛 = p * aa
    반지름 = max(1.2, min(hh, ww) / (1.6 if 어두움 else 4.0))
    번짐 = cv2.GaussianBlur(빛, (0, 0), 반지름)
    out = 255.0 - (255.0 - out) * (255.0 - 번짐 * (0.85 if 어두움 else 0.30)) / 255.0
    bg[y0:y1, x0:x1] = np.clip(out, 0, 255).astype(np.uint8)

    # 야간은 빛덩어리 전체가 불로 보이므로 번짐이 남는 범위까지 박스에 넣는다.
    if 어두움:
        밝기 = 번짐.max(axis=2)
        ys, xs = np.where(밝기 > 배경밝기 * 0.35 + 12)
    else:
        ys, xs = np.where(a > 0.3)
    if len(xs) < 4:
        return None
    return x0 + int(xs.min()), y0 + int(ys.min()), x0 + int(xs.max()) + 1, y0 + int(ys.max()) + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="fire_snowbg_20260923")
    ap.add_argument("--n-out", type=int, default=2000)
    ap.add_argument("--neg-frac", type=float, default=0.25, help="불을 안 얹은 배경의 비율")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--크기", default="보통", choices=["보통", "작게", "아주작게"],
                    help="얹을 불의 폭. 채점 편의 실제 불이 14~19px 이다")
    ap.add_argument("--채도", type=float, default=1.0, help="불의 채도 배수. 0.5 면 색이 반쯤 빠진다")
    ap.add_argument("--불종류", default="컬러", choices=["컬러", "흑백", "섞기"],
                    help="흑백 = 야간 적외선 편에서 뽑은 흰 불덩이만 쓴다")
    a = ap.parse_args()
    random.seed(a.seed)
    np.random.seed(a.seed)

    out = V / "data/학습데이터" / a.name
    (out / "images/train").mkdir(parents=True, exist_ok=True)
    (out / "labels/train").mkdir(parents=True, exist_ok=True)
    (out / "_preview").mkdir(parents=True, exist_ok=True)

    print("불꽃 조각 뽑는 중 (SAM2 불 폴리곤)")
    조각들 = 불꽃뽑기()
    if a.불종류 == "흑백":
        조각들 = [q for q in 조각들 if q.name.endswith("_흑백.png")]
    elif a.불종류 == "컬러":
        조각들 = [q for q in 조각들 if not q.name.endswith("_흑백.png")]
    print("  %s 조각 %d개" % (a.불종류, len(조각들)))
    flames = [cv2.imread(str(p), cv2.IMREAD_UNCHANGED) for p in 조각들]
    flames = [f for f in flames if f is not None and f.ndim == 3 and f.shape[2] == 4]
    print("불꽃 조각 %d개" % len(flames))
    print("배경 뽑는 중")
    bgs = 배경프레임()
    print("배경 %d장" % len(bgs))
    if not bgs or not flames:
        print("재료가 모자랍니다")
        return 1

    만든수 = 음성수 = 미리보기 = 0
    lines = []
    헛돔 = 0
    while 만든수 + 음성수 < a.n_out and 헛돔 < a.n_out * 20:
        음성 = random.random() < a.neg_frac
        후보 = bgs if 음성 else [b for b in bgs if b[0] in BG_POS]
        clip, t, fr = random.choice(후보)
        im = fr.copy()
        H, W = im.shape[:2]
        boxes = []
        if not 음성:
            for _ in range(random.choice([1, 1, 1, 2])):
                f = 흔들기(random.choice(flames))
                # 작은 쪽을 자주 뽑는다. 채점 편의 불이 14~19px 이라 큰 불만 배우면 소용없다
                lo, hi = OUT_W_BY_BG.get(clip, OUT_W)
                배 = {"보통": 1.0, "작게": 0.7, "아주작게": 0.5}[a.크기]
                lo, hi = max(8, int(lo * 배)), max(10, int(hi * 배))
                tw = int(min(hi, lo + (hi - lo) * random.random() ** 2))
                s = tw / max(1, f.shape[1])
                nh = max(8, int(f.shape[0] * s))
                fr2 = cv2.resize(f, (tw, nh), interpolation=cv2.INTER_AREA)
                # 하늘(위 32%)과 화면 맨 아래는 피한다. 불은 지면 가까이에서 난다.
                cx = random.randint(int(W * 0.08), int(W * 0.92))
                cy = random.randint(int(H * 0.32), int(H * 0.88))
                if a.채도 != 1.0:
                    hsv = cv2.cvtColor(fr2[:, :, :3], cv2.COLOR_BGR2HSV).astype(np.float32)
                    hsv[:, :, 1] *= a.채도
                    fr2 = np.dstack([cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR),
                                     fr2[:, :, 3]])
                r = 얹기(im, fr2, cx, cy)
                if r:
                    boxes.append(r)
            if not boxes:
                헛돔 += 1
                continue
        stem = "%s_%05.1f_%05d" % (clip, t, 만든수 + 음성수)
        cv2.imwrite(str(out / "images/train" / (stem + ".jpg")), im, [cv2.IMWRITE_JPEG_QUALITY, 92])
        with open(out / "labels/train" / (stem + ".txt"), "w") as fh:
            for x0, y0, x1, y1 in boxes:
                fh.write("%d %.6f %.6f %.6f %.6f\n" % (
                    FIRE_CLS, (x0 + x1) / 2 / W, (y0 + y1) / 2 / H, (x1 - x0) / W, (y1 - y0) / H))
        lines.append(str((out / "images/train" / (stem + ".jpg")).resolve()))
        if boxes and 미리보기 < 16:
            vis = im.copy()
            for x0, y0, x1, y1 in boxes:
                cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 255, 0), 2)
            cv2.imwrite(str(out / "_preview" / (stem + ".jpg")), vis)
            미리보기 += 1
        if 음성:
            음성수 += 1
        else:
            만든수 += 1
        if (만든수 + 음성수) % 200 == 0:
            print("  %d장" % (만든수 + 음성수), flush=True)

    (out / "train.txt").write_text("\n".join(lines) + "\n")
    (out / "data.yaml").write_text(
        "path: %s\ntrain: train.txt\nval: train.txt\nnames:\n  0: fire\n  1: smoke\n" % out.resolve())
    (out / "meta.json").write_text(json.dumps({
        "name": a.name, "mode": "fire",
        "what": "눈·안개 CCTV 배경에 SAM2 불 폴리곤으로 잘라 낸 실제 불꽃을 합성",
        "배경": BG_CLIPS,
        "배경출처": "KISA_악천후_사람(사람 항목 영상, 불 없음, 방화 학습 미사용)",
        "불출처": "자동라벨/sam2 객체1(불) · 주황 불꽃만 · kisa_연구개발_방화영상",
        "불꽃조각수": len(flames), "양성": 만든수, "음성": 음성수, "얹은폭px": list(OUT_W),
        "주의": "배경 9편은 방화 오경보 시험셋에서 빼야 한다(학습에 들어가므로)",
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n%s  양성 %d · 음성 %d  (견본 %s)" % (out, 만든수, 음성수, out / "_preview"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
