# -*- coding: utf-8 -*-
"""KISA 지능형 CCTV 4항목 SA 생성기 (오프라인 파일·RTSP 라이브 공용).

한 번 실행에 항목 하나만 고른다(게이팅). 시험은 항목별로 진행되고, 다른 항목의 경보가 SA 에 섞이면
'이벤트 종류 불일치' 오검이 되므로 선택한 항목의 AlarmDescription 만 기록한다.

  사전점검 : python tools/kisa_items.py --selfcheck
  오프라인 : python tools/kisa_items.py --item intrusion --videos <mp4 폴더> --maps <map 폴더> --gt <xml 폴더> --out KISAresult
  시험장   : python tools/kisa_items.py --item loitering --rtsp rtsp://192.168.0.2:8554/ \
                 --list c:/KISAlist/RTSP_streaming_list.xml --maps c:/KISAmap --out c:/KISAresult

규칙·파라미터는 배포용 채점에서 확정된 값(dash_v2 core.js · results/ALL_RESULTS.md) 을 그대로 옮겼다.
  intrusion  person_v3 + 3x3@960 타일 + 자체 IoU 트래커(0.5초) → '마지막 사람' 몸전체(꼭짓점3) 진입 시각.  92.86
  loitering  person_v2 + 같은 덤프 → 발끝 체류 6초면 배회자, '마지막 배회자' 진입 시각 + 10초.        93.10
  falldown   yolo11x-pose 10fps → 사람별 트랙 → 59차원×10초 창 → SeqNet → sigmoid≥0.269 연속 4창,
             트랙들 중 가장 이른 시각(처음 쓰러진 사람).                                             88.89
  fire       6뷰 타일(score_kisa 와 동일) → 결합 규칙(기본) 또는 신규칙(--fire-rule new). 모델 weights/kisa/fire_snowfull.pt.
             옛 경로(FireSmokeDetector ONNX + alarm_service) 는 --fire-legacy.

판정 로직은 app/services/kisa_rules.py 와 같은 의미이되, 라이브로 한 프레임씩 먹이며
'settle 로 확정된 순간'을 알아야 하므로 증분(incremental) 형태로 다시 썼다.
"""
import argparse
import math
import sys
import time
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))   # 옆의 rtsp_source.py
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

WEIGHTS = ROOT / "weights" / "kisa"
BEFORE_S, AFTER_S = 2.0, 10.0          # 정상검출 창: 정답 -2초 ~ +10초

ITEMS = {
    "intrusion": dict(desc="Intrusion", model="person_v3.pt", zone="Intrusion", stride=0.5, delay=0.0,
                      conf=0.45, corners=3, hold=2, settle=24.0, gap=2),
    # track_imgsz: 배포영상 1280x720 을 640 으로 줄여 통째로 넣고 있었다(타일 없음). 쓰러짐에서 같은 조건을
    # 960 으로 올리자 84.21→94.74 가 됐으므로 여기도 검증 대상. 기본은 기존 동작(640) 유지.
    "loitering": dict(desc="Loitering", model="person_v2.pt", zone="Loitering", stride=0.5, delay=10.0,
                      conf=0.40, corners=0, dwell=6.0, settle=5.0, gap=6, track_imgsz=640),
    # pose_imgsz: 배포영상이 1280x720 인데 640 으로 줄이면 먼 사람의 관절이 흔들려 트랙이 잘게 끊긴다.
    # 960 으로 올리자 분절이 크게 줄고(예: 41개→2개) 실패하던 편이 정검으로 바뀌었다(자체 10편 84.21→94.74).
    # th 0.269 -> 0.755 (2026-09-15). 0.269 는 확신 없는 초기 신호에도 터져 C00_235_0002 가 GT-3.5s 에 발화했다.
    # 자세 1280 확률 덤프로 문턱을 훑으니 0.70~0.81 구간에서만 10편 전부 정검이었다(그 밖은 전부 90.00).
    # 통로 가운데 0.755 를 쓴다. 아래 벽 0.70 = 235 의 이른 가짜 신호, 위 벽 0.82 = 가장 약한 진짜 낙상.
    # 전수 100.00 · LOOCV 90.00 (변별하는 편이 235 하나뿐이라 낙관 +10). 최악이어도 지금(90.00)과 같다.
    "falldown": dict(desc="Falldown", model="yolo11x-pose.pt", stride=0.1, delay=0.0, th=0.755, need=4,
                     pose_imgsz=1280),
    # 방화: score_kisa.py 와 같은 6뷰 타일(전체+4분할+중앙) → 표본별 최고 conf → 창 규칙. 기본 규칙 = '결합+타일가정 3/5'
    # (불 ≥0.4 또는 불 ≥0.3&연기 ≥0.6 이 5스텝 창에 3회). --fire-rule new 면 fire_rule2 신규칙(불 0.5 5/12 + 연기 기준선Δ0.2).
    # 규칙 변경(2026-09-15): 불 0.4 4회/6스텝 → 불 0.45 3회/10스텝, 연기 기준 사용 안 함.
    # 덤프 44개(클립 평가 440건) 합산에서 정검 +18 · 미검 -18 · 오검 -6.
    # 연기를 켜면 오검이 44 → 73~103 으로 늘어난다(안개편 C00_195_0001 은 연기가 0초부터 계속 높다).
    # smoke=1.1 은 "연기 조건을 절대 만족시키지 않는다"는 뜻이다(신뢰도는 1 을 넘을 수 없다).
    "fire": dict(desc="FireDetection", model="fire_snowfull.pt", stride=0.5, delay=10.0,
                 rule="combined", fire=0.45, smoke=1.1, win=10, hits=3, new_fire=0.5, new_win=12, new_hits=5, new_sdelta=0.2,
                 view_imgsz=640),
}
FIRE_NAMES = {0: "fire", 1: "smoke"}
# 타일 검출: 3x3 격자, 겹침 0.2, 입력 960, conf 0.15.
# 주의: person_redump.py 와 격자·해상도는 같지만 NMS 의 contain 이 다르다.
#   여기(process)는 contain=None -> 내부 2.0 = 부분검출 억제 끔
#   person_redump.py 는 기본 0.75 = 억제 켬  (--contain 2.0 으로 맞출 수 있다)
#   이 차이로 트랙이 달라져 같은 판정기를 써도 침입이 94.74 대 87.72 로 갈린다(2026-09-16 확인).
TILE = dict(grid=3, overlap=0.2, imgsz=960, conf=0.15)


def hms(sec):
    sec = max(0, int(round(sec)))
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def hms_to_s(text):
    h, m, s = (int(x) for x in str(text).strip().split(":"))
    return h * 3600 + m * 60 + s


# ----------------------------------------------------------------------------- SA / GT / 목록
def sa_xml(video_name, events, scenario=None, duration_s=None):
    """KISA SA 형식. 안내서 p.45 의 예시와 같은 형태로 쓴다.

    안내서가 SA 에 요구하는 Header 속성값은 둘뿐이다(p.45 표).
        <AlarmEvents>  이벤트 발생 개수
        <Filename>     영상 파일명
    배포 GT 에는 Scenario/Dataset/Libversion/Weather/DetectArea 같은 게 더 있지만 그건
    진흥원이 촬영 정보를 적어 둔 것이다. 안내서는 SA 와 GT 가 "유사하다" 고만 하지 같아야
    한다고 하지 않는다. 본시험은 제출 후 수정이 불가능하므로 명시된 예시와 글자 그대로
    같은 형태로 간다. (2026-09-15: GT 뼈대로 바꿨다가 안내서 원문 확인 후 되돌림)

    scenario·duration_s 는 받되 쓰지 않는다. 호출부가 이미 넘기고 있어서 자리만 남겨 둔다.

    이벤트가 여럿이면 발생 시각 순서대로 기록한다(p.46 복합 이벤트).
    이벤트 0개면 <Alarms></Alarms> 빈 태그로 쓴다. 자기닫힘 <Alarms /> 를 못 읽는 파서가
    있어 보수적인 쪽을 고른 것이고, 안내서에 명시된 내용은 아니다.
    """
    root = ET.Element("KisaLibraryIndex")
    clip = ET.SubElement(ET.SubElement(root, "Library"), "Clip")
    head = ET.SubElement(clip, "Header")
    ET.SubElement(head, "AlarmEvents").text = str(len(events))
    ET.SubElement(head, "Filename").text = video_name
    alarms = ET.SubElement(clip, "Alarms")
    for e in sorted(events, key=lambda x: x["start_s"]):
        al = ET.SubElement(alarms, "Alarm")
        ET.SubElement(al, "StartTime").text = hms(e["start_s"])
        ET.SubElement(al, "AlarmDescription").text = e["desc"]
        ET.SubElement(al, "AlarmDuration").text = hms(e.get("duration_s", 10))
    ET.indent(root, space="  ")
    xml = ET.tostring(root, encoding="unicode").replace("<Alarms />", "<Alarms></Alarms>")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml


def read_alarms(xml_path):
    out = []
    for al in ET.parse(xml_path).getroot().iter("Alarm"):
        st, desc = al.findtext("StartTime"), al.findtext("AlarmDescription")
        if st and desc:
            out.append({"start_s": hms_to_s(st), "desc": desc.strip()})
    return out


def read_list(src):
    """RTSP_streaming_list.xml (두 가지 스키마 모두) → 파일명 순서 목록."""
    text = Path(src).read_text(encoding="utf-8", errors="replace")
    root = ET.fromstring(text)
    names = [e.text.strip() for e in root.iter()
             if e.tag in ("Name", "FileName") and (e.text or "").strip()]
    if not names:
        raise ValueError(f"영상 목록이 비었다: {src}")
    return names


def zone_of(maps_dir, stem, tag, frame_wh=None):
    """영역파일 C00_140.map 에서 <Intrusion>/<Loitering> 다각형. 없으면 <DetectArea>, 그것도 없으면 화면 전체."""
    loc = "_".join(stem.split("_")[:2])
    f = Path(maps_dir) / (loc + ".map") if maps_dir else None
    if f is not None and f.exists():
        root = ET.parse(f).getroot()
        node = root.find(tag)
        if node is None:                 # Element 은 자식이 없으면 falsy 라 `or` 로 고르면 안 된다
            node = root.find("DetectArea")
        if node is not None:
            pts = [tuple(int(float(v)) for v in p.text.split(",")) for p in node.findall("Point")]
            if len(pts) >= 3:
                return pts
    print(f"[MAP] {stem}: 영역파일 없음/비정상({f}) → 화면 전체를 구역으로 씀", flush=True)
    w, h = frame_wh or (1280, 720)
    return [(0, 0), (w, 0), (w, h), (0, h)]


def score(pairs):
    """[(gt_alarms, sa_alarms)] → 정검/미검/오검/F1. 창 벗어난 경보 = 오검 + 그 정답은 미검."""
    tp = fn = fp = 0
    for gts, sas in pairs:
        left = list(sas)
        for g in gts:
            lo, hi = g["start_s"] - BEFORE_S, g["start_s"] + AFTER_S
            m = next((a for a in left if a["desc"] == g["desc"] and lo <= a["start_s"] <= hi), None)
            if m:
                left.remove(m); tp += 1
            else:
                fn += 1
        fp += len(left)
    r = tp / (tp + fn) if tp + fn else 0.0
    p = tp / (tp + fp) if tp + fp else 0.0
    f1 = 2 * r * p / (r + p) * 100 if r + p else 0.0
    return {"정상검출": tp, "미검출": fn, "오검출": fp, "검출률": round(r, 4), "정밀도": round(p, 4),
            "점수": round(f1, 2), "합격": f1 >= 90.0}


# ----------------------------------------------------------------------------- 사람 검출(타일) + 트래커
def tiles_of(fr, grid, overlap):
    h, w = fr.shape[:2]
    if grid <= 1:
        return [(fr, 0, 0)]
    out = []
    th, tw = h // grid, w // grid
    oy, ox = int(th * overlap), int(tw * overlap)
    for gy in range(grid):
        for gx in range(grid):
            y0 = max(0, gy * th - oy); y1 = min(h, (gy + 1) * th + oy)
            x0 = max(0, gx * tw - ox); x1 = min(w, (gx + 1) * tw + ox)
            out.append((fr[y0:y1, x0:x1], x0, y0))
    return out


def iou(a, b):
    ax1, ay1, ax2, ay2 = a; bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def contained(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    A = (a[2] - a[0]) * (a[3] - a[1])
    return inter / A if A > 0 else 0.0


def nms(dets, thr=0.5, contain=0.75):
    """겹침(IoU≥thr) + 부분검출(작은 박스가 큰 박스 안에 contain 이상) 제거. 타일 경계 이중검출 병합."""
    keep = []
    for d in sorted(dets, key=lambda d: -d[0]):
        if all(iou(d[1:], k[1:]) < thr and contained(d[1:], k[1:]) < contain for k in keep):
            keep.append(d)
    return keep


class Tracker:
    """IoU + 중심거리 단순 트래커(person_redump.py 와 같은 구현: iou_thr 0.25 · max_gap 10).
    원거리 인물이 간헐적으로 잡혀도 트랙을 잇는다."""

    def __init__(self, iou_thr=0.25, max_gap=10):
        self.iou_thr, self.max_gap = iou_thr, max_gap
        self.tracks, self.next_id = [], 1

    def update(self, dets):
        for t in self.tracks:
            t["miss"] += 1
        out, used = [], set()
        for conf, x1, y1, x2, y2 in sorted(dets, key=lambda d: -d[0]):
            box = (x1, y1, x2, y2)
            best, bi = self.iou_thr, None
            for i, t in enumerate(self.tracks):
                if i in used:
                    continue
                v = iou(box, t["box"])
                if v > best:
                    best, bi = v, i
            if bi is None:
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                dbest, di = 1e18, None
                for i, t in enumerate(self.tracks):
                    if i in used:
                        continue
                    tx1, ty1, tx2, ty2 = t["box"]
                    d = math.hypot(cx - (tx1 + tx2) / 2, cy - (ty1 + ty2) / 2)
                    lim = max(60.0, 0.8 * max(x2 - x1, y2 - y1)) * (1 + t["miss"])
                    if d < dbest and d <= lim:
                        dbest, di = d, i
                bi = di
            if bi is None:
                self.tracks.append({"id": self.next_id, "box": box, "miss": 0})
                used.add(len(self.tracks) - 1)
                out.append((self.next_id, round(conf, 3), *box))
                self.next_id += 1
            else:
                self.tracks[bi]["box"] = box; self.tracks[bi]["miss"] = 0; used.add(bi)
                out.append((self.tracks[bi]["id"], round(conf, 3), *box))
        self.tracks = [t for t in self.tracks if t["miss"] <= self.max_gap]
        return out


class PersonDetector:
    """타일 검출. contain=None 이면 겹침(IoU) NMS 만(부분검출 억제 끔), 값을 주면 부분검출 억제도 한다.
    배포 실측 94.74 는 contain=None(끔) + IntrusionRule 의 gap 조합에서 나왔다.
    dumps/intrusion_tile* 은 person_redump.py 가 억제를 켠 채(0.75) 만든 것이라 이 경로와 다르다."""

    def __init__(self, weights, tile=TILE, device=None, contain=None):
        from ultralytics import YOLO
        self.model = YOLO(str(weights))
        self.tile = tile
        self.device = device
        self.contain = contain

    def detect(self, bgr):
        dets = []
        for crop, ox, oy in tiles_of(bgr, self.tile["grid"], self.tile["overlap"]):
            r = self.model.predict(crop, conf=self.tile["conf"], imgsz=self.tile["imgsz"], classes=[0],
                                   verbose=False, device=self.device)[0]
            for b in r.boxes:
                x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
                dets.append((float(b.conf), x1 + ox, y1 + oy, x2 + ox, y2 + oy))
        return nms(dets, contain=self.contain if self.contain is not None else 2.0)


class BotSortPersons:
    """전체 프레임 person 검출 + ultralytics BoT-SORT 트랙 ID (server_tdump.py 와 동일: imgsz 640, conf 0.20, botsort).
    배회 93.1 은 이 덤프 위에서 나왔다. 세션(클립)마다 새로 만들어 트랙 상태를 끊는다."""

    def __init__(self, weights, conf=0.20, imgsz=640, device=None):
        from ultralytics import YOLO
        self.model = YOLO(str(weights)); self.conf, self.imgsz, self.device = conf, imgsz, device

    def update(self, bgr):
        r = self.model.track(bgr, persist=True, conf=self.conf, imgsz=self.imgsz, classes=[0],
                             verbose=False, tracker="botsort.yaml", device=self.device)[0]
        out = []
        if r.boxes is None or r.boxes.id is None:
            return out
        for b in r.boxes:
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            out.append((int(b.id[0]), round(float(b.conf), 3), x1, y1, x2, y2))
        return out


# ----------------------------------------------------------------------------- 구역 판정(kisa_rules 와 동일)
def in_poly(x, y, poly):
    inside = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def entered(box, poly, corners):
    """발끝(하단 중앙)이 구역 안 + corners 개 이상 꼭짓점이 구역 안. corners 0 = 발끝만(배회), 3 = 몸전체(침입)."""
    x1, y1, x2, y2 = box
    if not in_poly((x1 + x2) / 2, y2, poly):
        return False
    if corners <= 0:
        return True
    return sum(in_poly(cx, cy, poly) for cx, cy in ((x1, y1), (x2, y1), (x1, y2), (x2, y2))) >= corners


T_EPS = 0.2   # 시각 비교 여유(초). 파일 fps 30.0000253·RTSP pts 지터로 t 가 격자보다 조금 작아 settle 이 한 스텝 늦게 성립하는 일 방지(C00_039_0002 204.5→233.5 사례)


class IntrusionRule:
    """트랙별 몸전체 진입(hold 표본 연속) → 마지막 사람의 진입 시각. settle 초 동안 새 진입이 없으면 확정.
    gap = 연속 판정 중 허용하는 끊김 표본 수. 구역 경계에서 검출이 한 번 튀어도 같은 진입으로 이어간다
    (LoiterRule 에는 원래 있던 관용인데 침입 이식 때 빠져 있었다. 배포 30편 92.86 → 94.74)."""

    def __init__(self, poly, conf, corners, hold, settle, gap=2):
        self.poly, self.conf, self.corners, self.hold, self.settle = poly, conf, corners, hold, settle
        self.gap = gap
        self.streak, self.miss, self.entry = {}, {}, {}
        self.latest = self.last_new = None
        self.settled = None

    def feed(self, t, boxes):
        if self.settled is not None:
            return self.settled
        seen = set()
        for pid, conf, x1, y1, x2, y2 in boxes:
            if conf < self.conf or not entered((x1, y1, x2, y2), self.poly, self.corners):
                continue
            seen.add(pid)
            self.miss[pid] = 0
            self.streak[pid] = self.streak.get(pid, 0) + 1
            if self.streak[pid] == self.hold and pid not in self.entry:
                self.entry[pid] = t
                self.latest = t if self.latest is None else max(self.latest, t)
                self.last_new = t
        for pid in list(self.streak):
            if pid not in seen:
                self.miss[pid] = self.miss.get(pid, 0) + 1
                if self.miss[pid] > self.gap:                  # gap 표본까지는 streak 유지
                    self.streak[pid] = 0
        if self.latest is not None and t - self.last_new >= self.settle - T_EPS:
            self.settled = self.latest
        return self.settled

    def final(self):
        return self.settled if self.settled is not None else self.latest


class LoiterRule:
    """구역 발끝 체류 dwell 초(gap 프레임까지 끊김 허용) → 배회자. 마지막 배회자의 진입 시각(+delay 는 밖에서)."""

    def __init__(self, poly, conf, corners, dwell, settle, gap, step):
        self.poly, self.conf, self.corners = poly, conf, corners
        self.dwell_s, self.settle, self.gap, self.step = dwell, settle, gap, step
        self.dwell, self.miss, self.entry, self.loit = {}, {}, {}, {}
        self.latest = self.last_new = None
        self.settled = None

    def feed(self, t, boxes):
        if self.settled is not None:
            return self.settled
        seen = set()
        for pid, conf, x1, y1, x2, y2 in boxes:
            if conf < self.conf or not entered((x1, y1, x2, y2), self.poly, self.corners):
                continue
            seen.add(pid)
            if not self.dwell.get(pid, 0) > 0:
                self.entry[pid] = t
            self.dwell[pid] = self.dwell.get(pid, 0) + self.step
            self.miss[pid] = 0
            if self.dwell[pid] >= self.dwell_s and pid not in self.loit:
                self.loit[pid] = self.entry[pid]
                self.latest = self.entry[pid] if self.latest is None else max(self.latest, self.entry[pid])
                self.last_new = t
        for pid in list(self.dwell):
            if pid not in seen:
                self.miss[pid] = self.miss.get(pid, 0) + 1
                if self.miss[pid] > self.gap:
                    self.dwell[pid] = 0
        if self.latest is not None and t - self.last_new >= self.settle - T_EPS:
            self.settled = self.latest
        return self.settled

    def final(self):
        return self.settled if self.settled is not None else self.latest


# ----------------------------------------------------------------------------- 쓰러짐(fall_track.py 이식)
FALL_STRIDE, FALL_SUB, FALL_WIN, FALL_DIM = 0.1, 5, 20, 59
KP_TH, FALL_MAX_GAP, FALL_MAXP = 0.2, 8, 5


def kp_center(kp):
    v = kp[kp[:, 2] >= KP_TH]
    return None if len(v) == 0 else (float(v[:, 0].mean()), float(v[:, 1].mean()))


def feat_of(kp, W, H):
    """59차원: [conf, cx, cy, w, h, w/h, 몸통각/90, 목높이] + 17×(x,y,conf). 학습과 같은 방식."""
    v = kp[kp[:, 2] >= KP_TH]
    if len(v) == 0:
        return np.zeros(FALL_DIM, np.float32)
    x1, y1 = float(v[:, 0].min()), float(v[:, 1].min())
    x2, y2 = float(v[:, 0].max()), float(v[:, 1].max())
    w, h = max(x2 - x1, 1.0), max(y2 - y1, 1.0)
    conf = float(v[:, 2].mean())
    sh = [(kp[i][0], kp[i][1]) for i in (5, 6) if kp[i][2] >= KP_TH]
    hip = [(kp[i][0], kp[i][1]) for i in (11, 12) if kp[i][2] >= KP_TH]
    angle, neck_y = 90.0, 0.0
    if sh:
        neck_y = sum(p[1] for p in sh) / len(sh) / H
    if sh and hip:
        sx = sum(p[0] for p in sh) / len(sh); sy = sum(p[1] for p in sh) / len(sh)
        hx = sum(p[0] for p in hip) / len(hip); hy = sum(p[1] for p in hip) / len(hip)
        a = abs(math.degrees(math.atan2(hy - sy, hx - sx)))
        angle = min(a, 180 - a)
    base = [conf, (x1 + x2) / 2 / W, (y1 + y2) / 2 / H, w / W, h / H, w / max(1.0, h), angle / 90.0, neck_y]
    kflat = []
    for i in range(17):
        kflat += [float(kp[i][0]) / W, float(kp[i][1]) / H, float(kp[i][2])]
    return np.array(base + kflat, np.float32)


def build_seqnet():
    import torch.nn as nn

    class SeqNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv = nn.Sequential(nn.Conv1d(FALL_DIM, 96, 5, padding=2), nn.ReLU(),
                                      nn.Conv1d(96, 96, 5, padding=2), nn.ReLU())
            self.gru = nn.GRU(96, 96, num_layers=2, batch_first=True, bidirectional=True)
            self.head = nn.Linear(192, 1)

        def forward(self, x):
            h = self.conv(x.transpose(1, 2)).transpose(1, 2)
            h, _ = self.gru(h)
            return self.head(h[:, -1]).squeeze(-1)
    return SeqNet()


class FallJudge:
    """10fps 키포인트 → 트랙(중심거리 연결) → 0.5초마다 트랙별 최신 10초 창을 SeqNet 에 → 연속 need 창 돌파.
    fall_track.py 의 배치 계산을 프레임 단위 증분으로 옮긴 것. 첫 돌파 트랙 = 처음 쓰러진 사람."""

    def __init__(self, pose_weights, net_weights, th, need, device=None, pose_imgsz=640):
        import torch
        from ultralytics import YOLO
        self.pose = YOLO(str(pose_weights))
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.net = build_seqnet().to(self.device)
        self.net.load_state_dict(torch.load(str(net_weights), map_location=self.device))
        self.net.eval()
        self.th, self.need = th, need
        self.pose_imgsz = pose_imgsz
        self.i = 0                 # 0.1초 프레임 번호
        self.WH = None
        self.tracks = []           # {"frames": {i: kp}, "last_c", "last_i", "xs": [feat], "pres": [bool], "ts": [t], "run": 0, "fired": None}
        self.decided = None

    def _link(self, kps):
        dets = [(kp, c) for kp in kps if (c := kp_center(kp)) is not None]
        used = set()
        for kp, c in dets:
            best, bestd = None, 1e18
            for k, tr in enumerate(self.tracks):
                if k in used or self.i - tr["last_i"] > FALL_MAX_GAP:
                    continue
                d = math.hypot(c[0] - tr["last_c"][0], c[1] - tr["last_c"][1])
                lim = 120.0 + 40.0 * (self.i - tr["last_i"])
                if d < bestd and d <= lim:
                    best, bestd = k, d
            if best is None:
                self.tracks.append({"frames": {self.i: kp}, "last_c": c, "last_i": self.i,
                                    "xs": [], "pres": [], "ts": [], "run": 0, "fired": None})
                used.add(len(self.tracks) - 1)
            else:
                tr = self.tracks[best]; tr["frames"][self.i] = kp; tr["last_c"] = c; tr["last_i"] = self.i
                used.add(best)

    def feed(self, t, bgr):
        import torch
        if self.decided is not None:
            return self.decided
        if self.WH is None:
            self.WH = (bgr.shape[1], bgr.shape[0])
        r = self.pose.predict(bgr, conf=0.10, imgsz=self.pose_imgsz, verbose=False, device=self.device)[0]
        kps = []
        if r.keypoints is not None and len(r.boxes):
            confs = [float(b.conf) for b in r.boxes]
            idx = np.argsort(confs)[::-1][:FALL_MAXP]
            kdata = r.keypoints.data.cpu().numpy()
            kps = [kdata[j] for j in idx]
        self._link(kps)
        # 0.5초 슬롯이 닫힐 때(5프레임마다) 트랙별 피처 1개 추가 + 창 판정
        if (self.i + 1) % FALL_SUB == 0:
            lo = self.i + 1 - FALL_SUB
            W, H = self.WH
            slot_t = t - (FALL_SUB - 1) * FALL_STRIDE          # 슬롯 시작 시각(= fall_track 의 ts[idx])
            for tr in self.tracks:
                # fall_track.py(배치)와 동일하게: 트랙이 끊긴 뒤에도 0벡터를 계속 이어 붙인다.
                # 쓰러진 뒤 검출이 끊기는(누운 사람 conf 급락) 패턴은 창 끝에 0이 이어지는 모양이라 여기서 발화한다.
                kp = next((tr["frames"][k] for k in range(lo, self.i + 1) if k in tr["frames"]), None)
                tr["xs"].append(feat_of(kp, W, H) if kp is not None else np.zeros(FALL_DIM, np.float32))
                tr["pres"].append(kp is not None); tr["ts"].append(slot_t)
                if len(tr["xs"]) > 4 * FALL_WIN:                 # 메모리: 창 계산에 필요한 만큼만 유지
                    del tr["xs"][:-2 * FALL_WIN]; del tr["pres"][:-2 * FALL_WIN]; del tr["ts"][:-2 * FALL_WIN]
                if len(tr["frames"]) < FALL_WIN // 2:            # 배치의 min_present(10프레임 미만 트랙 제외)
                    continue
                if tr["fired"] is None:
                    # 배치(fall_track.py)는 트랙 시계열을 영상 전체 타임라인에 놓아 등장 전 구간이 0벡터다.
                    # 그래서 트랙이 생긴 직후(존재 5슬롯)부터 20슬롯 창이 평가된다. 여기서도 앞을 0으로 채워 같게 맞춘다.
                    # (안 채우면 등장 10초 뒤부터 평가 → 등장 후 곧 쓰러지는 짧은 트랙을 통째로 놓친다: 060·153·217 미검 원인)
                    seg = tr["xs"][-FALL_WIN:]; pres = tr["pres"][-FALL_WIN:]
                    if len(seg) < FALL_WIN:
                        pad = FALL_WIN - len(seg)
                        seg = [np.zeros(FALL_DIM, np.float32)] * pad + seg; pres = [False] * pad + pres
                    if sum(pres) < FALL_WIN // 4:
                        continue                                 # 배치는 이런 창을 목록에서 빼기만 한다(연속 카운터 유지)
                    with torch.no_grad():
                        z = float(self.net(torch.tensor(np.stack(seg)[None], dtype=torch.float32,
                                                        device=self.device)).cpu()[0])
                    p = 1.0 / (1.0 + math.exp(-z))
                    tr.setdefault("curve", []).append((round(float(tr["ts"][-1]), 2), round(z, 3)))   # 디버그: (창끝 시각, 로짓)
                    tr["run"] = tr["run"] + 1 if p >= self.th else 0
                    if tr["run"] >= self.need:
                        tr["fired"] = tr["ts"][-self.need]           # 연속 돌파 첫 창의 시각
                        self.decided = tr["fired"] if self.decided is None else min(self.decided, tr["fired"])
        self.i += 1
        return self.decided

    def final(self):
        return self.decided


# ----------------------------------------------------------------------------- 방화(score_kisa.py 규칙 이식)
class FireJudge:
    """6뷰 타일 추론 → 표본별 (t, 불max, 연기max) → 창 규칙으로 onset. score_kisa.py 의 dump()+onset() 과 같은 계산.
    rule='combined': 불 ≥fire 또는 (불 ≥0.3 & 연기 ≥smoke) 가 win 스텝 안에 hits 회 → 창의 첫 충족 시각.
    rule='new'     : fire_rule2 — 불 ≥new_fire 또는 연기 ≥ 앞 60초 기준선(80퍼센타일)+new_sdelta(&≥0.3), new_win/new_hits."""

    def __init__(self, weights, cfg, device=None):
        from ultralytics import YOLO
        self.model = YOLO(str(weights)); self.cfg = cfg; self.device = device
        self.rows = []; self.win = deque(maxlen=cfg["new_win"] if cfg["rule"] == "new" else cfg["win"])
        self.decided = None

    def _baseline(self):
        head = sorted(s for t, f, s in self.rows if t <= 60.0)
        return head[min(int(len(head) * 0.8), len(head) - 1)] if head else 0.0

    def feed(self, t, bgr):
        if self.decided is not None:
            return self.decided
        h, w = bgr.shape[:2]
        crops = [bgr] + [bgr[y:y + h // 2, x:x + w // 2] for x, y in
                         ((0, 0), (w // 2, 0), (0, h // 2), (w // 2, h // 2), (w // 4, h // 4))]
        best = {"fire": 0.0, "smoke": 0.0}
        for r in self.model.predict(crops, conf=0.05, imgsz=self.cfg.get("view_imgsz", 640),
                                    verbose=False, device=self.device):
            for b in r.boxes:
                name = FIRE_NAMES.get(int(b.cls))
                if name in best:
                    best[name] = max(best[name], float(b.conf))
        f, s = best["fire"], best["smoke"]
        self.rows.append((t, f, s))
        c = self.cfg
        if c["rule"] == "new":
            hit = f >= c["new_fire"] or (s >= self._baseline() + c["new_sdelta"] and s >= 0.3)
            need = c["new_hits"]
        else:
            hit = f >= c["fire"] or (f >= 0.3 and s >= c["smoke"])
            need = c["hits"]
        self.win.append((t, hit))
        if sum(1 for _, x in self.win if x) >= need:
            self.decided = next(t0 for t0, x in self.win if x)
        return self.decided

    def final(self):
        return self.decided


# ----------------------------------------------------------------------------- 오프라인 프레임 소스
class _Frame:
    __slots__ = ("session", "ts", "bgr")

    def __init__(self, session, ts, bgr):
        self.session, self.ts, self.bgr = session, ts, bgr


class FileSource:
    """mp4 목록을 차례로 읽어 stride_s 간격 프레임을 낸다. 세션 = 파일명. (app.vision.FileSource 와 같은 인터페이스,
    검증 하네스가 앱 설정에 묶이지 않도록 cv2 만으로 다시 썼다.)"""

    def __init__(self, paths, stride_s=0.5):
        import cv2
        self.cv2, self.paths, self.stride_s = cv2, [Path(p) for p in paths], stride_s
        self._cap = None; self._idx = -1; self._i = 0; self._fps = 30.0; self._step = 1

    def _open_next(self):
        while True:
            self._idx += 1
            if self._idx >= len(self.paths):
                return False
            cap = self.cv2.VideoCapture(str(self.paths[self._idx]))
            if not cap.isOpened():
                print(f"[SRC] 열기 실패, 건너뜀: {self.paths[self._idx].name}", flush=True); continue
            self._cap = cap
            self._fps = cap.get(self.cv2.CAP_PROP_FPS) or 30.0
            self._step = max(1, int(round(self._fps * self.stride_s))); self._i = 0
            return True

    def read(self):
        while True:
            if self._cap is None and not self._open_next():
                return None
            if not self._cap.grab():                       # grab 만 하고 필요한 프레임만 디코드(빠름)
                self._cap.release(); self._cap = None; continue
            i, self._i = self._i, self._i + 1
            if i % self._step:
                continue
            ok, frame = self._cap.retrieve()
            if not ok:
                continue
            return _Frame(self.paths[self._idx].name, i / self._fps, frame)


# ----------------------------------------------------------------------------- 세션 실행
def make_judge(item, cfg, stem, maps_dir, frame_wh, dets):
    if item == "intrusion":
        poly = zone_of(maps_dir, stem, cfg["zone"], frame_wh)
        return IntrusionRule(poly, cfg["conf"], cfg["corners"], cfg["hold"], cfg["settle"], cfg["gap"])
    if item == "loitering":
        poly = zone_of(maps_dir, stem, cfg["zone"], frame_wh)
        return LoiterRule(poly, cfg["conf"], cfg["corners"], cfg["dwell"], cfg["settle"], cfg["gap"], cfg["stride"])
    raise ValueError(item)


def process(item, src, out_dir, maps_dir=None, expect=None, gt_dir=None, device=None, conf=None):
    """src.read() 가 Frame(session, ts, bgr) 를 내는 소스(FileSource/RtspSource)를 끝까지 돌려 세션마다 SA 를 쓴다."""
    cfg = dict(ITEMS[item])
    if conf is not None and "conf" in cfg:
        cfg["conf"] = conf
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    det = None; fall = None
    if item == "intrusion":
        det = PersonDetector(WEIGHTS / cfg["model"], device=device, contain=None)   # 원본 92.86 덤프 = IoU NMS 만
    tracker = judge = None
    session = None; last_ts = 0.0; onset = None; done = {}
    t_start = time.time(); n_frames = 0

    def finish():
        nonlocal session, onset
        if session is None:
            return
        o = onset if onset is not None else (judge.final() if judge else None)
        events = []
        if o is not None:
            start = o + cfg["delay"]
            events = [{"start_s": start, "duration_s": max(0.0, last_ts - start), "desc": cfg["desc"]}]
        (out / (Path(session).stem + ".xml")).write_text(
            sa_xml(session, events, cfg["desc"], last_ts), encoding="utf-8")
        done[session] = events
        print(f"  {session} → {'SA ' + hms(events[0]['start_s']) + (' (확정)' if onset is not None else ' (영상끝 미확정)') if events else 'SA 없음'}", flush=True)
        session = None; onset = None

    while True:
        f = src.read()
        if f is None:
            break
        if f.session != session:
            finish()
            session = f.session; stem = Path(session).stem
            print(f"[클립] {session} 시작", flush=True)
            wh = (f.bgr.shape[1], f.bgr.shape[0])
            if item == "falldown":
                judge = FallJudge(WEIGHTS / cfg["model"], WEIGHTS / "fall_track.pt", cfg["th"], cfg["need"], device,
                                  cfg.get("pose_imgsz", 640))
            elif item == "fire":
                judge = FireJudge(WEIGHTS / cfg["model"], cfg, device)
            elif item == "loitering":
                tracker = BotSortPersons(WEIGHTS / cfg["model"], device=device,
                                         imgsz=cfg.get("track_imgsz", 640))   # 원본 93.1 덤프 = BoT-SORT 전체프레임
                judge = make_judge(item, cfg, stem, maps_dir, wh, None)
            else:
                tracker = Tracker()
                judge = make_judge(item, cfg, stem, maps_dir, wh, det)
        last_ts = f.ts; n_frames += 1
        if n_frames % 200 == 0:
            print(f"[진행] {session} {f.ts:.0f}초", flush=True)
        if onset is not None:
            continue                                   # 확정 뒤엔 프레임만 소비(세션 끝까지 시각 유지)
        if item in ("falldown", "fire"):
            onset = judge.feed(f.ts, f.bgr)
        elif item == "loitering":
            onset = judge.feed(f.ts, tracker.update(f.bgr))
        else:
            boxes = tracker.update(det.detect(f.bgr))
            onset = judge.feed(f.ts, boxes)
    finish()
    for n in (expect or []):
        if n not in done:
            (out / (Path(n).stem + ".xml")).write_text(
                sa_xml(n, [], cfg["desc"]), encoding="utf-8"); done[n] = []
            print(f"  {n} → 못 받음, 빈 SA", flush=True)
    print(f"SA {len(done)}건 → {out.resolve()}  ({n_frames}프레임, {time.time() - t_start:.0f}s)", flush=True)

    if gt_dir:
        pairs, rows = [], []
        for n, evs in done.items():
            g = Path(gt_dir) / (Path(n).stem + ".xml")
            gts = read_alarms(g) if g.exists() else []
            sas = [{"start_s": e["start_s"], "desc": e["desc"]} for e in evs]
            pairs.append((gts, sas))
            gt0 = gts[0]["start_s"] if gts else None; sa0 = sas[0]["start_s"] if sas else None
            v = ("정검" if gt0 is not None and sa0 is not None and gt0 - BEFORE_S <= sa0 <= gt0 + AFTER_S
                 else "미검" if sa0 is None else "오검")
            rows.append(f"  클립 {Path(n).stem}: {v} (gt={gt0} sa={None if sa0 is None else round(sa0, 1)})")
        print("\n".join(rows))
        s = score(pairs)
        print(f"[{item}] 정검 {s['정상검출']} 미검 {s['미검출']} 오검 {s['오검출']} → 점수 {s['점수']:.2f} "
              f"{'합격' if s['합격'] else '(90 미달)'}", flush=True)
    return done


def cfg_line(item):
    """지금 이 실행이 쓰는 설정을 한 줄로. 로그에 남아 대시보드가 읽는다.

    항목마다 쓰는 값이 달라서 공통 필드만 고르고 나머지는 항목별로 붙인다.
    """
    c = ITEMS[item]
    parts = [f"항목={item}", f"모델={c['model']}", f"주기={c['stride']}s"]
    if item == "intrusion":
        parts += [f"해상도={TILE['imgsz']}", f"타일={TILE['grid']}x{TILE['grid']}", f"겹침={TILE['overlap']}",
                  f"conf={c['conf']}", f"꼭짓점={c['corners']}", f"연속={c['hold']}",
                  f"끊김허용={c['gap']}", f"확정대기={c['settle']}s"]
    elif item == "loitering":
        parts += [f"해상도={c.get('track_imgsz', 640)}", "추적=BoT-SORT",
                  f"conf={c['conf']}", f"체류={c['dwell']}s", f"끊김허용={c['gap']}",
                  f"확정대기={c['settle']}s", f"지연={c['delay']}s"]
    elif item == "falldown":
        parts += [f"해상도={c.get('pose_imgsz', 640)}", "판정=SeqNet",
                  f"임계={c['th']}", f"연속창={c['need']}"]
    elif item == "fire":
        parts += [f"해상도={c.get('view_imgsz', 640)}", "뷰=6분할타일",
                  f"규칙={c['rule']}", f"불={c['fire']}", f"연기={c['smoke']}",
                  f"창={c['win']}", f"히트={c['hits']}", f"지연={c['delay']}s"]
    return " ".join(parts)


# ----------------------------------------------------------------------------- 자체 점검
def selfcheck():
    # SA 형식
    x = sa_xml("C00_001_0030.mp4", [{"start_s": 12, "duration_s": 5, "desc": "Intrusion"}])
    for tag in ("<KisaLibraryIndex>", "<AlarmEvents>1</AlarmEvents>", "<Filename>C00_001_0030.mp4</Filename>",
                "<StartTime>00:00:12</StartTime>", "<AlarmDescription>Intrusion</AlarmDescription>", "<AlarmDuration>00:00:05</AlarmDuration>"):
        assert tag in x, tag
    assert "<Alarms></Alarms>" in sa_xml("a.mp4", [])
    # 안내서 p.45 예시와 같은 형태인가. GT 뼈대로 바꿨다가 되돌린 자리라 못을 박아 둔다.
    assert x.startswith('<?xml version="1.0" encoding="UTF-8"?>'), "선언"
    assert x.index("<AlarmEvents>") < x.index("<Filename>"), "Header 순서(AlarmEvents 먼저)"
    for tag in ("<Scenario>", "<Dataset>", "<Libversion>", "<Duration>"):
        assert tag not in x, f"SA 에 없어야 할 태그: {tag}"
    # 설정 한 줄이 네 항목 모두 만들어지는가(키 오타면 실행 첫 줄에서 터진다)
    for _it in ITEMS:
        assert "모델=" in cfg_line(_it), _it
    # 타일이 화면을 빈틈없이 덮는가
    fr = np.zeros((720, 1280, 3), np.uint8)
    cov = np.zeros((720, 1280), bool)
    for crop, ox, oy in tiles_of(fr, 3, 0.2):
        cov[oy:oy + crop.shape[0], ox:ox + crop.shape[1]] = True
    assert cov.all(), "타일 빈틈"
    # nms: 부분검출 병합
    assert len(nms([(0.9, 0, 0, 100, 200), (0.5, 10, 10, 90, 100)])) == 1
    # 트래커: 같은 사람 유지, 끊김 허용
    tr = Tracker()
    a = tr.update([(0.9, 100, 100, 150, 250)])[0][0]
    tr.update([]); b = tr.update([(0.9, 104, 102, 154, 252)])[0][0]
    assert a == b == 1, (a, b)
    # 침입: 두 사람이 10초, 30초에 진입 → 마지막 사람(30) · settle 24초 뒤 확정
    poly = [(0, 0), (1280, 0), (1280, 720), (0, 720)]
    ir = IntrusionRule(poly, 0.45, 3, 2, 24.0)
    t = 0.0; got = None
    while t < 80:
        boxes = []
        if t >= 10: boxes.append((1, 0.9, 100, 100, 150, 300))
        if t >= 30: boxes.append((2, 0.9, 400, 100, 450, 300))
        got = ir.feed(t, boxes)
        if got is not None: break
        t += 0.5
    assert got == 30.5 and abs(t - 54.5) < 1e-6, (got, t)      # hold 2 → 진입 30.5, settle 24 → 54.5 에 확정
    # 배회: 6초 체류 후 배회자, 진입시각 반환(+10 은 밖에서)
    lr = LoiterRule(poly, 0.4, 0, 6.0, 5.0, 6, 0.5)
    got = None
    for k in range(60):
        got = lr.feed(k * 0.5, [(1, 0.9, 100, 100, 150, 300)] if k >= 4 else [])
        if got is not None: break
    assert got == 2.0, got
    # 창 밖 경보 = 오검 + 미검
    G = [{"start_s": 100, "desc": "Intrusion"}]
    assert score([(G, [{"start_s": 110, "desc": "Intrusion"}])])["정상검출"] == 1
    s = score([(G, [{"start_s": 111, "desc": "Intrusion"}])]); assert s["오검출"] == 1 and s["미검출"] == 1
    assert score([(G, [{"start_s": 100, "desc": "Loitering"}])])["오검출"] == 1, "종류 불일치 = 오검"
    # 쓰러짐 피처 차원·SeqNet 형태
    kp = np.zeros((17, 3), np.float32); kp[:, 2] = 0.9; kp[:, 0] = np.linspace(100, 200, 17); kp[:, 1] = np.linspace(100, 400, 17)
    assert feat_of(kp, 1280, 720).shape == (FALL_DIM,)
    import torch
    net = build_seqnet(); out = net(torch.zeros(2, FALL_WIN, FALL_DIM)); assert out.shape == (2,)
    if (WEIGHTS / "fall_track.pt").exists():
        net.load_state_dict(torch.load(str(WEIGHTS / "fall_track.pt"), map_location="cpu"))
    # RTSP 백엔드. PyAV 가 없으면 default_backend 가 OpenCV 로 조용히 떨어지는데,
    # 그 경로는 pts 를 안 주고 전송방식도 못 고른다 = 절대 pts·TCP→UDP 폴백이 무력화된다.
    # 조용히 성능이 깎이는 종류라 여기서 막는다.
    try:
        import av                                            # noqa: F401
    except ImportError:
        raise SystemExit("[실패] PyAV 없음. RTSP 가 OpenCV 로 떨어져 절대 pts 를 잃는다. 이미지를 다시 빌드할 것")
    from rtsp_source import RtspSource, default_backend       # noqa: F401
    print("selfcheck OK (PyAV", av.__version__ + ")")


def main():
    ap = argparse.ArgumentParser(description="KISA 4항목 SA 생성기 (항목 하나만 선택)")
    ap.add_argument("--item", choices=list(ITEMS), help="시험 항목")
    ap.add_argument("--videos", help="오프라인: mp4 폴더")
    ap.add_argument("--rtsp", help="시험장: RTSP 주소 (예 rtsp://192.168.0.2:8554/)")
    ap.add_argument("--list", dest="vlist", help="RTSP_streaming_list.xml (영상 순서 = SA 파일명)")
    ap.add_argument("--maps", default="", help="영역파일(.map) 폴더 (침입·배회)")
    ap.add_argument("--gt", help="GT xml 폴더 (있으면 채점)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / 'KISAresult'),
                    help='SA XML 저장 폴더. 인자를 빼면 _kisa_port/KISAresult (절대경로). c:/KISAresult 는 KISA 안내문의 예시일 뿐 OS·경로는 지정돼 있지 않다.')
    ap.add_argument("--conf", type=float, default=None, help="사람 conf 임계 덮어쓰기(침입 .45 / 배회 .40)")
    ap.add_argument("--device", default=None, help="cuda / cpu (기본 자동)")
    ap.add_argument("--scene-thresh", type=float, default=None)
    ap.add_argument("--fire-rule", choices=["combined", "new"], default=None, help="방화 규칙: combined(기본, 결합+타일가정 3/5) / new(fire_rule2 신규칙)")
    ap.add_argument("--fire-weights", default=None, help="방화 .pt (기본 weights/kisa/fire_snowfull.pt)")
    ap.add_argument("--person-weights", default=None, help="사람 .pt 덮어쓰기(침입·배회 공통). 학습 실험 채점용")
    ap.add_argument("--person-imgsz", type=int, default=None,
                    help="사람 추론 해상도 덮어쓰기(침입 타일·배회 전체프레임 공통). 학습 해상도와 맞춘다")
    ap.add_argument("--fire-legacy", action="store_true", help="방화를 옛 경로(weights/best.onnx + alarm_service)로")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()

    if a.selfcheck:
        selfcheck(); return
    if not a.item:
        ap.error("--item 이 필요하다")
    if a.item == "fire":
        if a.fire_rule:
            ITEMS["fire"]["rule"] = a.fire_rule
        if a.fire_weights:
            ITEMS["fire"]["model"] = a.fire_weights        # 절대경로면 WEIGHTS / 경로 가 그대로 절대경로가 된다
        if a.fire_legacy:
            from tools import kisa as fire_tool
            if a.rtsp:
                names = read_list(a.vlist) if a.vlist else None
                fire_tool.run_rtsp(a.rtsp, str(ROOT / "weights" / "best.onnx"), names, a.out, 640, a.scene_thresh)
            else:
                fire_tool.run(a.videos, str(ROOT / "weights" / "best.onnx"), a.gt, a.out, 640)
            return

    if a.person_weights:                                  # 침입·배회가 사람 검출 모델을 공유한다(항목 분기 밖이어야 한다)
        ITEMS["intrusion"]["model"] = a.person_weights
        ITEMS["loitering"]["model"] = a.person_weights
    if a.person_imgsz:                                    # 학습 해상도와 추론 해상도가 어긋나면 점수가 무너진다
        TILE["imgsz"] = a.person_imgsz                    # 침입: 3x3 타일 입력 크기
        ITEMS["loitering"]["track_imgsz"] = a.person_imgsz

    stride = ITEMS[a.item]["stride"]
    print(f"[설정] {cfg_line(a.item)}", flush=True)
    if a.rtsp:
        # RTSP 는 앱의 소스(세션 경계·재연결) 그대로 쓴다. 배포본에는 앱 패키지가 없으므로
        # 같은 폴더의 발췌본을 먼저 찾는다(내용은 원본과 동일).
        try:
            from rtsp_source import RtspSource
        except ImportError:
            from app.vision.frame_sources import RtspSource
        names = read_list(a.vlist) if a.vlist else None
        # 시험장은 우리 프로그램을 먼저 켜고 담당자가 'Video load' 를 누른다 → 첫 연결을 오래(30분) 기다려야 한다
        src = RtspSource(a.rtsp, names=names, stride_s=stride, scene_thresh=a.scene_thresh,
                         retry_s=2.0, max_retry=900, abs_pts=True)
        print(f"[KISA {a.item}] {a.rtsp} 수신 대기 (목록 {len(names) if names else '없음'}편, 주기 {stride}s)", flush=True)
        process(a.item, src, a.out, a.maps, names, None, a.device, a.conf)
    else:
        vids = sorted(p for p in Path(a.videos).iterdir() if p.suffix.lower() == ".mp4")
        if not vids:
            raise SystemExit(f"mp4 가 없다: {a.videos}")
        gt = a.gt or (a.videos if any(v.with_suffix(".xml").exists() for v in vids) else None)
        process(a.item, FileSource(vids, stride_s=stride), a.out, a.maps, [v.name for v in vids], gt, a.device, a.conf)


if __name__ == "__main__":
    main()
