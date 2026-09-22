# -*- coding: utf-8 -*-
"""침입 판정 규칙의 대안 구조들을 덤프로 훑는다. 추론은 하지 않는다.

왜 (2026-09-18)
    지금 규칙은 conf 하나를 30편 전체에 똑같이 건다. 낮추면 약한 편(구역 안 최고 0.189)은
    살지만 강한 편이 일찍 터져 창 밖으로 나간다(오검+미검 이중 감점). 그래서 conf 를
    0.10 까지 내려도 총점이 94.74 를 못 넘었다.
    편마다 문턱이 달라지거나, 약한 증거를 따로 세거나, 지나가는 사람을 거르면
    그 상충을 피할 수 있는지 본다.

세 가지 대안
    rel   상대 문턱. 그 편 앞구간의 구역 안 신뢰도 분포(퍼센타일) + delta 를 문턱으로 쓴다.
          편마다 배경 수준이 다른 것을 흡수한다. 방화의 rule='new' 와 같은 발상이다.
    weak  약한 증거 누적. 강한 검출(>=hi)은 1점, 약한 검출(lo~hi)은 w점.
          창(win) 안에서 합이 need 이상이면 인정. 약한 신호가 여러 번 쌓이는 것을 받는다.
    dirin 진입 방향. 구역 밖에서 안으로 들어온 트랙만 인정한다.
          지나가던 사람이 스쳐서 생기는 이른 오경보를 거른다.

공통
    settle 초 동안 새 진입이 없으면 확정(지금 규칙과 같다). 점수는 제출 도구의 K.score 를 쓴다.

사용
    python scripts/intr_rule2.py [덤프폴더 ...]
"""
import itertools
import json
import sys
from collections import defaultdict, deque
from pathlib import Path

V = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V / "_kisa_port/tools"))
sys.path.insert(0, str(V / "scripts"))
import kisa_items as K   # noqa: E402
import kisa_paths as KP  # noqa: E402

CFG = K.ITEMS["intrusion"]
STEP = CFG["stride"]


def load(dump):
    d = Path(dump)
    rows, poly, gt = {}, {}, {}
    for f in sorted(d.glob("*.jsonl")):
        s = f.stem
        rows[s] = [json.loads(l) for l in f.read_text().splitlines()]
        poly[s] = K.zone_of(str(KP.ZONE_MAPS), s, CFG["zone"], (1280, 720))
        g = next(KP.videos("침입").rglob(s + ".xml"), None)
        a = K.read_alarms(g) if g else []
        gt[s] = a[0]["start_s"] if a else None
    return rows, poly, gt


def _pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    i = min(len(v) - 1, max(0, int(round((len(v) - 1) * p))))
    return v[i]


def sa_rel(rows, poly, corners, hold, settle, gap, base_s, pct, delta, floor):
    """상대 문턱: 앞 base_s 초 동안 구역 안에서 본 신뢰도의 pct 분위 + delta. 최소 floor."""
    hist = deque()                      # (t, conf) 구역 안에서 본 것들
    streak, miss, entry = {}, {}, {}
    latest = last_new = None
    for r in rows:
        t = r["t"]
        while hist and t - hist[0][0] > base_s:
            hist.popleft()
        th = max(floor, (_pct([c for _, c in hist], pct) or 0.0) + delta)
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            inside = K.entered((x1, y1, x2, y2), poly, corners)
            if inside:
                hist.append((t, conf))
            if conf < th or not inside:
                continue
            seen.add(pid)
            if streak.get(pid, 0) == 0:
                entry[pid] = t
            streak[pid] = streak.get(pid, 0) + 1
            miss[pid] = 0
            if streak[pid] >= hold:
                if latest is None or entry[pid] > latest:
                    latest, last_new = entry[pid], t
        for pid in list(streak):
            if pid in seen:
                continue
            miss[pid] = miss.get(pid, 0) + 1
            if miss[pid] > gap:
                streak[pid] = 0
        if latest is not None and last_new is not None and t - last_new >= settle:
            return latest
    return latest


def sa_weak(rows, poly, corners, settle, gap, lo, hi, w, win, need):
    """약한 증거 누적: 창(win 초) 안에서 강한 검출 1점 + 약한 검출 w점의 합이 need 이상."""
    pts = defaultdict(deque)            # 트랙 -> (t, 점수)
    entry, latest, last_new = {}, None, None
    for r in rows:
        t = r["t"]
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if not K.entered((x1, y1, x2, y2), poly, corners):
                continue
            sc = 1.0 if conf >= hi else (w if conf >= lo else 0.0)
            if sc <= 0:
                continue
            q = pts[pid]
            if not q:
                entry[pid] = t
            q.append((t, sc))
            while q and t - q[0][0] > win:
                q.popleft()
            if not q:
                entry.pop(pid, None); continue
            entry.setdefault(pid, q[0][0])
            if sum(x for _, x in q) >= need:
                e = q[0][0]
                if latest is None or e > latest:
                    latest, last_new = e, t
        for pid in list(pts):            # 오래 끊기면 창을 비운다
            q = pts[pid]
            while q and t - q[0][0] > win + gap * STEP:
                q.popleft()
            if not q:
                entry.pop(pid, None)
        if latest is not None and last_new is not None and t - last_new >= settle:
            return latest
    return latest


def sa_dirin(rows, poly, conf_th, corners, hold, settle, gap, out_need):
    """진입 방향: 구역 밖에서 out_need 표본 이상 보이다가 안으로 들어온 트랙만 인정."""
    outside = defaultdict(int)
    streak, miss, entry, ok = {}, {}, {}, set()
    latest = last_new = None
    for r in rows:
        t = r["t"]
        seen = set()
        for pid, conf, x1, y1, x2, y2 in r["boxes"]:
            if conf < conf_th:
                continue
            inside = K.entered((x1, y1, x2, y2), poly, corners)
            if not inside:
                outside[pid] += 1
                continue
            if outside.get(pid, 0) >= out_need:
                ok.add(pid)
            if pid not in ok:
                continue
            seen.add(pid)
            if streak.get(pid, 0) == 0:
                entry[pid] = t
            streak[pid] = streak.get(pid, 0) + 1
            miss[pid] = 0
            if streak[pid] >= hold:
                if latest is None or entry[pid] > latest:
                    latest, last_new = entry[pid], t
        for pid in list(streak):
            if pid in seen:
                continue
            miss[pid] = miss.get(pid, 0) + 1
            if miss[pid] > gap:
                streak[pid] = 0
        if latest is not None and last_new is not None and t - last_new >= settle:
            return latest
    return latest


def run(rows, poly, gt, fn, kw):
    pairs, miss = [], []
    for s in rows:
        sa = fn(rows[s], poly[s], **kw)
        pairs.append(([{"start_s": gt[s], "desc": "I"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "I"}] if sa is not None else []))
        if gt[s] is not None and (sa is None or not (gt[s] - 2 <= sa <= gt[s] + 10)):
            miss.append(s.replace("C00_", ""))
    return K.score(pairs), miss


GRIDS = {
    "rel": (sa_rel, dict(corners=[0, 2, 3], hold=[1, 2, 3], settle=[24.0], gap=[2],
                         base_s=[30.0, 60.0], pct=[0.8, 0.9, 0.95],
                         delta=[0.05, 0.10, 0.15, 0.20], floor=[0.10, 0.15, 0.20])),
    "weak": (sa_weak, dict(corners=[0, 2, 3], settle=[24.0], gap=[2],
                           lo=[0.12, 0.15, 0.20], hi=[0.35, 0.45], w=[0.3, 0.5],
                           win=[3.0, 5.0, 8.0], need=[2.0, 3.0, 4.0])),
    "dirin": (sa_dirin, dict(conf_th=[0.15, 0.20, 0.25, 0.30, 0.40, 0.45],
                             corners=[0, 2, 3], hold=[1, 2, 3], settle=[24.0], gap=[2],
                             out_need=[1, 2, 4])),
}

for dump in sys.argv[1:] or ["dumps/intrusion_tile_v3"]:
    rows, poly, gt = load(dump)
    if not rows:
        print("%s: 덤프 없음" % dump); continue
    base = run(rows, poly, gt, lambda rr, pp, **k: None, {})
    now = K.IntrusionRule
    # 지금 규칙 기준선
    pairs, bmiss = [], []
    for s in rows:
        j = now(poly[s], CFG["conf"], CFG["corners"], CFG["hold"], CFG["settle"], CFG["gap"])
        for r in rows[s]:
            j.feed(r["t"], r["boxes"])
        sa = j.final()
        pairs.append(([{"start_s": gt[s], "desc": "I"}] if gt[s] is not None else [],
                      [{"start_s": sa, "desc": "I"}] if sa is not None else []))
        if gt[s] is not None and (sa is None or not (gt[s] - 2 <= sa <= gt[s] + 10)):
            bmiss.append(s.replace("C00_", ""))
    b = K.score(pairs)
    print("\n===== %s   %d편" % (dump, len(rows)))
    print("  지금 규칙            %6.2f  (정검 %2d 미검 %d 오검 %d)  못잡음 %s"
          % (b["점수"], b["정상검출"], b["미검출"], b["오검출"], bmiss))
    for name, (fn, grid) in GRIDS.items():
        keys = list(grid)
        best, n = [], 0
        for vals in itertools.product(*grid.values()):
            kw = dict(zip(keys, vals))
            r, m = run(rows, poly, gt, fn, kw)
            best.append((r["점수"], kw, r, m)); n += 1
        best.sort(key=lambda x: -x[0])
        top = best[0][0]
        flat = sum(1 for sc, *_ in best if sc >= top - 0.01)
        print("  %-5s %4d조합  최고 %6.2f  (정검 %2d 미검 %d 오검 %d)  고원 %d개 %s"
              % (name, n, top, best[0][2]["정상검출"], best[0][2]["미검출"], best[0][2]["오검출"],
                 flat, "(믿을 만)" if flat >= 5 else "(봉우리·과적합 의심)"))
        print("        못잡음 %s" % best[0][3])
        print("        설정   %s" % {k: v for k, v in best[0][1].items()})
