# -*- coding: utf-8 -*-
"""serve_kisa.py 리팩토링 + SAM2 개선 요구사항(교정 전파·객체별 독립 마스크·공동/분리/DINO+SAM 전파 방식·융합 감지).
코어(sam2_mask_pts, _mask_bbox, 모델 로드·워밍업)는 그대로. sam2_propagate_objs 는 요구사항 1~3 을 위해 확장한다."""
import io, re, sys
p = sys.argv[1] if len(sys.argv) > 1 else "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "def label_file(" not in s, "이미 적용됨"

def rep(old, new, n=1):
    global s
    assert s.count(old) == n, (s.count(old), old[:100])
    s = s.replace(old, new)

def cut_between(start_marker, end_marker):
    """start_marker 로 시작하는 곳부터 end_marker 직전까지 지운다(둘 다 유일해야 한다)."""
    global s
    assert s.count(start_marker) == 1, (s.count(start_marker), start_marker[:80])
    i = s.index(start_marker)
    j = s.index(end_marker, i + len(start_marker))
    s = s[:i] + s[j:]

def cut_route(path):
    """do_GET/do_POST 안의 `if p == "<path>":` 블록 하나를 다음 라우트 시작까지 지운다."""
    global s
    start = f'        if p == "{path}"'
    assert s.count(start) == 1, (s.count(start), path)
    i = s.index(start)
    m = re.compile(r"\n        (?:if p |m = re\.match|self\.send_error\(404\))").search(s, i + len(start))
    s = s[:i] + s[m.start() + 1:]

# ---------- 0. 모듈 설명 ----------
cut_between('"""통합 KISA 검수 대시보드 서버', "import json, os, re, shutil, threading, time, urllib.parse")
s = s.replace("# -*- coding: utf-8 -*-\n", '''# -*- coding: utf-8 -*-
"""KISA 검수 대시보드 서버(서버에서 실행, ssh -L 8890 으로 로컬 브라우저 접속).

라벨 저장소 셋(표시·학습 우선순위 순):
  손라벨   data/학습데이터/손라벨/{person,fire}_labels.json   /api/savelabel · /api/labels · /api/clearlabels
  SAM 전파 data/학습데이터/자동라벨/sam2/<stem>.json         /api/sam2_propagate_start(큐) · sam2_jobs · sam2_cancel · sam2_label · sam2_drop · sam2_clear · sam2frames
  DINO     data/학습데이터/자동라벨/dino/<stem>.json         /api/autolabel · autolabel_drop (배치 스크립트가 만든다. 첫 등장 프레임 찾기·초안용)
  정답     data/학습데이터/정답라벨/<stem>.json               /api/gtlabel (읽기 전용)
손라벨 박스가 있는 프레임은 SAM 저장소에서 빠진다(savelabel 이 빼고, 전파 저장이 건너뛴다).
SAM: /api/sam2_mask(한 프레임 점·박스 → 마스크), /api/fuse_detect(Grounding DINO 박스 → SAM 마스크, 화재), 전파 방식 PROP_DEFAULT_MODE.
데이터 확인: /api/sources · raw · clips · clipconds · clipinfo · frameat · warmframes · dsimg · dslabel · rawlabel · vid
결과: /api/meta · dataset · results · queue
"""
''', 1)

# ---------- 1. 공통 헬퍼(라벨 파일·JSON 읽기/쓰기·프레임 키·NMS) ----------
rep('''_CLIPS = {}       # 카테고리별 영상 목록 캐시
''', '''_CLIPS = {}       # 카테고리별 영상 목록 캐시


def label_file(kind):
    """손라벨 파일. kind == "person" 이면 사람, 아니면 화재."""
    fn = "person_labels.json" if kind == "person" else "fire_labels.json"
    return data_path("data/학습데이터/손라벨/" + fn, fn)


def read_json(path, default):
    try:
        path = Path(path)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except Exception:
        return default


def write_json(path, obj):
    """임시 파일에 쓰고 바꿔 넣는다(쓰다 죽어도 반쪽 파일이 남지 않는다). 프로세스마다 임시 이름이 다르다."""
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8"); tmp.replace(path)


def tkey(t):
    """저장소 프레임 키. 0.5초 격자(사람 2FPS)로 맞춘 "190.5" 꼴. 화재(1초)도 같은 격자 위에 있다."""
    return f"{round(float(t) * 2) / 2:.1f}"


def nms_keep(dets, iou_th=0.4, cover_th=0.9):
    """dets = [(score, x1, y1, x2, y2, ...)] 점수순으로 겹침(IoU)·포함(한쪽이 90% 이상 덮임) 중복을 뺀다."""
    def _ov(a, b):
        ix1 = max(a[0], b[0]); iy1 = max(a[1], b[1]); ix2 = min(a[2], b[2]); iy2 = min(a[3], b[3])
        inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
        sa = (a[2] - a[0]) * (a[3] - a[1]); sb = (b[2] - b[0]) * (b[3] - b[1]); ua = sa + sb - inter
        return (inter / ua if ua > 0 else 0.0, max(inter / sa if sa > 0 else 0.0, inter / sb if sb > 0 else 0.0))
    keep = []
    for d in sorted(dets, key=lambda x: -x[0]):
        if all((lambda v: v[0] < iou_th and v[1] < cover_th)(_ov(d[1:5], k[1:5])) for k in keep):
            keep.append(d)
    return keep
''')
rep('''            import json as _json
            d = _json.load(open(jp, encoding="utf-8"))''', '''            d = json.load(open(jp, encoding="utf-8"))''')
# 캐시 새로고침이 프레임 캐시까지 지우지 않게(목록 캐시 json 만)
rep('''    _SOURCES = None; _RAW.clear(); _CLIPS.clear(); _CI.clear()
    shutil.rmtree(CACHE_DIR, ignore_errors=True)''', '''    _SOURCES = None; _RAW.clear(); _CLIPS.clear(); _CI.clear(); _CONDS.clear(); _AUTOL.clear()
    for f in CACHE_DIR.glob("*.json"):                # 폴더 스캔 결과만. 뽑아 둔 프레임(frames/)은 그대로
        try: f.unlink()
        except Exception: pass''')
# RAW_CLASS_NOTE 는 clipstat(삭제) 전용
cut_between("# 원본 클래스 규약이 우리(0=불,1=연기)와 다른 세트.", "_RAW = {}          # 카테고리별 파일 목록 캐시")
# read_frame: 설명문을 함수 머리로
rep('''def read_frame(clip, sec, w=0):
    _c = frame_cache_path(clip, sec, w)                    # 이미 뽑아 둔 게 있으면 바로 준다
    try:
        if _c.exists():
            return _c.read_bytes()
    except Exception:
        pass
    """그 시각(초)의 프레임 한 장을 JPEG 바이트로. 없으면 None.
    라벨은 초당 1장 기준이라 프레임 번호가 아니라 초로 받는다.
    w 를 주면 그 가로 픽셀로 줄여 보낸다(참조 샷 썸네일)."""
    mp4 = under_raw(clip, ".mp4")''', '''def read_frame(clip, sec, w=0):
    """그 시각(초)의 프레임 한 장을 JPEG 바이트로. 없으면 None. w 를 주면 그 가로 픽셀로 줄인다(썸네일). 디스크 캐시 우선."""
    _c = frame_cache_path(clip, sec, w)
    try:
        if _c.exists():
            return _c.read_bytes()
    except Exception:
        pass
    mp4 = under_raw(clip, ".mp4")''')
rep('''    q = 92
    if w and 0 < int(w) < fr.shape[1]:      # 썸네일은 작게·가볍게
        wh = int(round(fr.shape[0] * int(w) / fr.shape[1]))
        fr = cv2.resize(fr, (int(w), wh), interpolation=cv2.INTER_AREA)
        q = 78
    ok, buf = cv2.imencode(".jpg", fr, [int(cv2.IMWRITE_JPEG_QUALITY), q])
    if not ok:
        return None
    data = buf.tobytes()
    try:                                                   # 다음 요청은 디코딩 없이''', '''    data = _encode(fr, w)
    if data is None:
        return None
    try:                                                   # 다음 요청은 디코딩 없이''')

# ---------- 2. 죽은 모델 경로 제거: person_v3 · 옛 GDINO(사람) · sam2_box · 단일/다중 참조 전파 · 배경 DINO ----------
cut_between("_PERSON_MODEL = None\ndef person_boxes(", "_GDINO = None\nGDINO_PROMPT =")
cut_between("def gdino_boxes(clip, sec, th=0.30):", "AUTOLABEL_DIR = G / ")
rep('''_SAM2 = None
SAM2_ID = "facebook/sam2.1-hiera-small"
SAM2_MIN_SCORE = 0.60          # 이보다 낮으면 마스크가 화면 전체로 번지는 실패 사례가 나온다
''', '''_SAM2 = None
SAM2_ID = "facebook/sam2.1-hiera-small"
''')
cut_between("def sam2_box(clip, sec, px, py):", "_CONDS = {}\n")
cut_between("def sam2_propagate(clip, t_seed, box=None, point=None, back=15.0, fwd=15.0, step=0.5):", "_EMB_CACHE = {}")
rep('''_EMB_CACHE = {}                 # (clip, 초) → SAM2 이미지 임베딩
_FRAME_PREP = {}''', '''_FRAME_PREP = {}''')
cut_between("def sam2_propagate_multi(clip, seeds, back=10.0, fwd=10.0, step=0.5):", "def sam2_propagate_objs(")
cut_between("_BG_DINO = {}                   # clip", "_PROP_JOBS = {}")

# ---------- 3. 전파 코어 확장(요구 1·2·3): 점 프롬프트 · 구간 지정 · 객체별 독립 임계 · 분리/공동/DINO+SAM 방식 · 윤곽선 저장 ----------
rep('''def sam2_propagate_objs(clip, seeds, back=5.0, fwd=10.0, step=0.5, progress=None):
    """여러 객체를 한 세션에서 전파. seeds = [{"t": 초, "box": [x,y,w,h], "obj": 번호}]
    반환 ({시각: {obj: [x,y,w,h]}}, 걸린초, 오류)"""
    global _SAM2V
    import numpy as np, torch, time
    if not seeds:
        return {}, 0, "참조샷 없음"
    ts = [float(x["t"]) for x in seeds]
    t0 = max(0.0, min(ts) - float(back)); t1 = max(ts) + float(fwd)
    frames, times, W, H = _read_frames(clip, t0, t1, float(step))
    if not frames:
        return {}, 0, "프레임 없음"
''', '''PROP_DEFAULT_MODE = "separate"   # 전파 방식 기본값: separate(객체별 독립 세션) · joint(한 세션) · detect(프레임마다 DINO+SAM). eval_prop_modes.py 결과로 정한다
PROP_THR = {1: 0.0, 2: 0.0}      # 객체별 마스크 로짓 임계(독립 적용). 연기(2)를 낮추면 흐린 연기를 더 담는다


def _poly_of(arr, W, H, eps=0.004):
    """이진 마스크 → 가장 큰 윤곽선(정규화 좌표, 단순화). 화면에 객체별 층으로 그린다."""
    import cv2
    cs, _ = cv2.findContours((arr > 0).astype("uint8"), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return []
    c = max(cs, key=cv2.contourArea)
    c = cv2.approxPolyDP(c, eps * cv2.arcLength(c, True), True)
    return [[round(float(q[0][0]) / W, 4), round(float(q[0][1]) / H, 4)] for q in c]


def _seed_inputs(sd, W, H):
    """참조샷 하나 → SAM2 비디오 세션 입력(픽셀 박스 + 있으면 포함/제외 점). 점만 있고 박스가 없는 참조도 된다."""
    kw = {}
    b = sd.get("box")
    if b:
        kw["input_boxes"] = [[[float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]]]
    pts = [q for q in (sd.get("pts") or []) if len(q) >= 3]
    if pts:
        kw["input_points"] = [[[[float(q[0]) * W, float(q[1]) * H] for q in pts]]]
        kw["input_labels"] = [[[int(q[2]) for q in pts]]]
    return kw


def sam2_propagate_objs(clip, seeds, back=5.0, fwd=10.0, step=0.5, progress=None, a=None, b=None, mode=None, thr=None):
    """여러 객체 전파. seeds = [{"t": 초, "box": [x,y,w,h], "obj": 번호, "pts": [[x,y,label],...]}]
    구간: a·b(초)를 주면 그 구간만(교정 전파), 없으면 참조샷 앞뒤 back·fwd 초.
    mode: separate(객체마다 독립 세션·독립 임계 → 서로 뭉개지지 않는다) · joint(한 세션에 전 객체) · detect(프레임마다 DINO 박스 → SAM 마스크)
    반환 ({시각: {obj: [x,y,w,h]}}, {시각: {obj: 윤곽선}}, 걸린초, 오류)"""
    global _SAM2V
    import numpy as np, torch, time
    mode = mode or PROP_DEFAULT_MODE
    thr = {int(k): float(v) for k, v in (thr or PROP_THR).items()}
    if not seeds:
        return {}, {}, 0, "참조샷 없음"
    ts = [float(x["t"]) for x in seeds]
    t0 = max(0.0, min(ts) - float(back)) if a is None else max(0.0, float(a))
    t1 = (max(ts) + float(fwd)) if b is None else float(b)
    seeds = [sd for sd in seeds if t0 - 1e-6 <= float(sd["t"]) <= t1 + 1e-6]   # 구간 밖 참조는 이번 전파에 안 쓴다
    if not seeds:
        return {}, {}, 0, "구간 안 참조샷 없음"
    if mode == "detect":
        return propagate_detect(clip, seeds, t0, t1, float(step), progress)
    frames, times, W, H = _read_frames(clip, t0, t1, float(step))
    if not frames:
        return {}, {}, 0, "프레임 없음"
''')
rep('''    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    out = {}
    if progress is not None:
        progress["total"] = len(frames) * len(by_obj); progress["done"] = 0

    def to_px(b):
        return [float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]
''', '''    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    out, polys = {}, {}
    if progress is not None:
        progress["total"] = len(frames) * (1 if mode == "joint" else len(by_obj)); progress["done"] = 0
''')
rep('''    def run_segment(oid, i0, i1, seed_i, box, prof, rev):
        """frames[i0..i1] 구간을 seed_i(구간 안 인덱스) 의 박스 하나로 조건 걸고 rev 방향으로 전파."""
        if i1 < i0:
            return
        sub = frames[i0:i1 + 1]
        sess = proc.init_video_session(video=sub, inference_device=dev, dtype=torch.float32)
        proc.add_inputs_to_inference_session(sess, frame_idx=seed_i - i0, obj_ids=[oid], input_boxes=[[to_px(box)]], original_size=(H, W))
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=seed_i - i0, reverse=rev):
            gi = i0 + int(r.frame_idx)
            if progress is not None:
                if progress.get("cancel"):
                    raise RuntimeError("cancelled")
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            sc = r.object_score_logits
            if sc is not None and float(sc.detach().flatten()[0]) <= 0:      # 대상 없음(가림·이탈)
                continue
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2:
                arr = arr[0]
            bb = _mask_bbox(arr)
            if bb is None:
                continue
            x1, y1, x2, y2 = bb
            area = (x2 - x1) * (y2 - y1)
            sa = area_at(prof, times[gi]) or area
            if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 3.0:     # 근처 참조 박스 대비 3배 넘게 커지거나 1/3 아래 = 흘러감
                continue
            out.setdefault(f"{times[gi]:.1f}", {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5),
                                                                 round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]
        del sess
        torch.cuda.empty_cache()

    with torch.no_grad():
        for oid in sorted(by_obj):
            sds = sorted(by_obj[oid], key=lambda sd: float(sd["t"]))
            prof = [(float(sd["t"]), float(sd["box"][2]) * W * float(sd["box"][3]) * H) for sd in sds]
            idxs = [fidx(sd["t"]) for sd in sds]
            # 1) 구간 시작 → 첫 참조 (역방향)
            run_segment(oid, 0, idxs[0], idxs[0], sds[0]["box"], prof, True)
            # 2) 참조 k → 참조 k+1 직전 (정방향), 마지막 참조 → 끝
            for k, sd in enumerate(sds):
                i0 = idxs[k]
                i1 = (idxs[k + 1] - 1) if k + 1 < len(sds) else (len(frames) - 1)
                if k + 1 < len(sds) and idxs[k + 1] == i0:    # 같은 프레임에 참조가 둘이면 뒤 것만
                    continue
                run_segment(oid, i0, max(i0, i1), i0, sd["box"], prof, False)
    return out, round(time.time() - tic, 1), None
''', '''    def take(gi, oid, arr, prof):
        """한 프레임·한 객체의 이진 마스크 → 박스·윤곽선 기록. 참조 박스 넓이 대비 3배/1/3 밖이면 흘러간 것으로 버린다."""
        bb = _mask_bbox(arr)
        if bb is None:
            return
        x1, y1, x2, y2 = bb
        area = (x2 - x1) * (y2 - y1)
        sa = area_at(prof, times[gi]) or area
        if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 3.0:
            return
        k = f"{times[gi]:.1f}"
        out.setdefault(k, {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5), round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]
        polys.setdefault(k, {})[str(oid)] = _poly_of(arr, W, H)

    def tick():
        if progress is not None:
            if progress.get("cancel"):
                raise RuntimeError("cancelled")
            progress["done"] = min(progress.get("done", 0) + 1, progress["total"])

    def masks_of(r, oids):
        """전파 결과 한 프레임 → {obj: 이진 마스크}. 객체마다 자기 임계로 독립 이진화(argmax 없음 → 불·연기가 서로를 지우지 않는다)."""
        pm = r.pred_masks.unsqueeze(0).cpu().float() if r.pred_masks.ndim == 3 else r.pred_masks.cpu().float()
        sc = r.object_score_logits
        res = {}
        for j, oid in enumerate(oids):
            if sc is not None and sc.numel() > j and float(sc.detach().flatten()[j]) <= 0:   # 대상 없음(가림·이탈)
                continue
            one = pm[:, j:j + 1] if pm.shape[1] > j else pm
            m = proc.post_process_masks(one, [(H, W)], binarize=True, mask_threshold=thr.get(oid, 0.0))[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2:
                arr = arr[0]
            res[oid] = arr
        return res

    def run_segment(inputs, i0, i1, seed_i, profs, rev):
        """frames[i0..i1] 구간. inputs = {obj: 참조샷} 를 seed_i 프레임에 조건으로 넣고 rev 방향으로 전파."""
        if i1 < i0 or not inputs:
            return
        sess = proc.init_video_session(video=frames[i0:i1 + 1], inference_device=dev, dtype=torch.float32)
        oids = sorted(inputs)
        for oid in oids:
            proc.add_inputs_to_inference_session(sess, frame_idx=seed_i - i0, obj_ids=[oid], original_size=(H, W), **_seed_inputs(inputs[oid], W, H))
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=seed_i - i0, reverse=rev):
            gi = i0 + int(r.frame_idx); tick()
            for oid, arr in masks_of(r, oids).items():
                take(gi, oid, arr, profs.get(oid) or [])
        del sess
        torch.cuda.empty_cache()

    def prof_of(sds):
        return [(float(sd["t"]), float(sd["box"][2]) * W * float(sd["box"][3]) * H) for sd in sds if sd.get("box")]

    with torch.no_grad():
        if mode == "joint":
            # 공동: 참조 시각의 합집합으로 구간을 나누고, 각 구간 시작에 모든 객체를 한 세션에 넣는다(구간 시작에 참조가 없는 객체는 가장 가까운 참조 박스)
            profs = {oid: prof_of(sorted(sds, key=lambda sd: float(sd["t"]))) for oid, sds in by_obj.items()}
            tset = sorted({fidx(sd["t"]) for sd in seeds})
            def nearest(oid, i):
                return min(by_obj[oid], key=lambda sd: abs(fidx(sd["t"]) - i))
            run_segment({oid: nearest(oid, tset[0]) for oid in by_obj}, 0, tset[0], tset[0], profs, True)
            for k, i0 in enumerate(tset):
                i1 = (tset[k + 1] - 1) if k + 1 < len(tset) else (len(frames) - 1)
                run_segment({oid: nearest(oid, i0) for oid in by_obj}, i0, max(i0, i1), i0, profs, False)
        else:
            # 분리(기본): 객체마다 자기 세션. 구간 = [시작 → 첫 참조](역방향), [참조 k → 참조 k+1)(정방향), [마지막 참조 → 끝]
            for oid in sorted(by_obj):
                sds = sorted(by_obj[oid], key=lambda sd: float(sd["t"]))
                profs = {oid: prof_of(sds)}
                idxs = [fidx(sd["t"]) for sd in sds]
                run_segment({oid: sds[0]}, 0, idxs[0], idxs[0], profs, True)
                for k, sd in enumerate(sds):
                    i0 = idxs[k]
                    i1 = (idxs[k + 1] - 1) if k + 1 < len(sds) else (len(frames) - 1)
                    if k + 1 < len(sds) and idxs[k + 1] == i0:    # 같은 프레임에 참조가 둘이면 뒤 것만
                        continue
                    run_segment({oid: sd}, i0, max(i0, i1), i0, profs, False)
    return out, polys, round(time.time() - tic, 1), None


# ---------- Grounding DINO(zero-shot 박스) + SAM2(마스크) 융합: 형태가 모호한 연기용 ----------
_GDINO = None
GDINO_FIRE_PROMPT = "fire. flame. smoke."
GDINO_PERSON_PROMPT = "a person. a pedestrian. a human. a man walking. a person with an umbrella."


def gdino_detect(fr_bgr, prompt, th=0.25):
    """프레임(BGR) 한 장에서 프롬프트의 물체 박스. 반환 [(score, x1, y1, x2, y2, label)] 픽셀, 중복 제거."""
    global _GDINO
    import cv2, torch
    h0, w0 = fr_bgr.shape[:2]
    if _GDINO is None:                       # 첫 호출에만 로드(대시보드 기동을 무겁게 하지 않는다)
        from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
        mid = "IDEA-Research/grounding-dino-base"
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _GDINO = (AutoProcessor.from_pretrained(mid), AutoModelForZeroShotObjectDetection.from_pretrained(mid).to(dev).eval(), dev)
    proc, model, dev = _GDINO
    rgb = cv2.cvtColor(fr_bgr, cv2.COLOR_BGR2RGB)
    with torch.no_grad():
        inp = proc(images=rgb, text=prompt, return_tensors="pt").to(dev)
        r = proc.post_process_grounded_object_detection(model(**inp), inp.input_ids, threshold=float(th), text_threshold=float(th), target_sizes=[(h0, w0)])[0]
    labels = r.get("text_labels") or r.get("labels") or [""] * len(r["scores"])
    dets = [(float(sc), *[float(v) for v in bx], str(lb)) for sc, bx, lb in zip(r["scores"], r["boxes"], labels)]
    return nms_keep(dets)


def _frame_bgr(clip, sec):
    """프레임 한 장(BGR). 디스크 캐시 → 없으면 영상에서 뽑는다."""
    import cv2, numpy as np
    data = read_frame(clip, sec, 0)
    if data is None:
        return None
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def fuse_detect(clip, sec, th=0.25):
    """화재 프레임: DINO 로 불·연기 박스를 찾고 SAM2 로 마스크를 따서 객체(1 불 · 2 연기)마다 가장 점수 높은 하나를 돌려준다.
    반환 {obj: {"box": [x,y,w,h], "poly": [...], "score": DINO 점수, "label": 텍스트}}"""
    fr = _frame_bgr(clip, sec)
    if fr is None:
        return {}
    h0, w0 = fr.shape[:2]
    best = {}
    for sc, x1, y1, x2, y2, lb in gdino_detect(fr, GDINO_FIRE_PROMPT, th):
        obj = 2 if "smoke" in lb.lower() else 1
        if obj in best and best[obj]["score"] >= sc:
            continue
        nb = [round(x1 / w0, 5), round(y1 / h0, 5), round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)]
        bx, poly, s2 = sam2_mask_pts(clip, sec, [], nb)
        best[obj] = {"box": bx or nb, "poly": poly or [], "score": round(sc, 3), "sam": round(float(s2), 3), "label": lb}
    return best


def propagate_detect(clip, seeds, t0, t1, step, progress=None):
    """전파 방식 detect: 프레임마다 DINO 박스 → 참조/직전 박스와 가장 가까운 것을 그 객체로 → SAM 마스크.
    시간 기억이 없어 SAM2 전파보다 흔들리지만 연기처럼 형태가 바뀌는 대상에서 이탈이 없다. 비교 실험용."""
    import time
    tic = time.time()
    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    ts = []
    t = t0
    while t <= t1 + 1e-6:
        ts.append(round(t, 2)); t = round(t + step, 3)
    if progress is not None:
        progress["total"] = len(ts); progress["done"] = 0
    fr0 = _frame_bgr(clip, ts[0]) if ts else None
    if fr0 is None:
        return {}, {}, 0, "프레임 없음"
    h0, w0 = fr0.shape[:2]
    last = {oid: min(sds, key=lambda sd: abs(float(sd["t"]) - t0))["box"] for oid, sds in by_obj.items()}   # 객체별 직전 박스(정규화)
    out, polys = {}, {}

    def iou(a, b):
        x1 = max(a[0], b[0]); y1 = max(a[1], b[1]); x2 = min(a[0] + a[2], b[0] + b[2]); y2 = min(a[1] + a[3], b[1] + b[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        return inter / (a[2] * a[3] + b[2] * b[3] - inter or 1.0)

    for t in ts:
        if progress is not None:
            if progress.get("cancel"):
                raise RuntimeError("cancelled")
            progress["done"] += 1
        for oid, sds in by_obj.items():                 # 참조 프레임은 참조 박스를 그대로 쓴다
            hit = next((sd for sd in sds if abs(float(sd["t"]) - t) < 1e-3), None)
            if hit:
                last[oid] = hit["box"]
        fr = _frame_bgr(clip, t)
        if fr is None:
            continue
        dets = gdino_detect(fr, GDINO_FIRE_PROMPT, 0.2)
        for oid in by_obj:
            want_smoke = (oid == 2)
            cands = []
            for sc, x1, y1, x2, y2, lb in dets:
                if ("smoke" in lb.lower()) != want_smoke:
                    continue
                nb = [x1 / w0, y1 / h0, (x2 - x1) / w0, (y2 - y1) / h0]
                ref = last.get(oid)
                v = iou(nb, ref) if ref else 0.0
                cx = nb[0] + nb[2] / 2 - (ref[0] + ref[2] / 2 if ref else 0.5); cy = nb[1] + nb[3] / 2 - (ref[1] + ref[3] / 2 if ref else 0.5)
                cands.append((v, -(cx * cx + cy * cy), sc, nb))
            cands = [c for c in cands if c[0] > 0.05 or -c[1] < 0.02]   # 직전 박스와 겹치거나 아주 가까운 것만
            if not cands:
                continue
            _, _, sc, nb = max(cands)
            bx, poly, _s = sam2_mask_pts(clip, t, [], nb)
            if not bx:
                continue
            k = f"{t:.1f}"
            out.setdefault(k, {})[str(oid)] = [round(v, 5) for v in bx]
            polys.setdefault(k, {})[str(oid)] = poly or []
            last[oid] = bx
    return out, polys, round(time.time() - tic, 1), None
''')

# ---------- 4. 큐·저장소: 윤곽선 저장, 결과 본문은 저장 뒤 버림, 중복 전파는 오류로 ----------
rep('''        try:
            frames, sec, err = sam2_propagate_objs(st["clip_full"], st["seeds"], back=st["back"], fwd=st["fwd"], step=st["step"], progress=st)
            st["result"] = frames; st["err"] = err; st["sec"] = sec
            if frames and not err:                       # 서버가 바로 저장 → 브라우저가 떠나 있어도 결과가 남는다
                sam2_store_write(st["clip_full"], frames, [{"t": q["t"], "obj": q.get("obj", 1), "box": q["box"]} for q in st["seeds"]])
                st["saved"] = True
        except Exception as e:
            st["err"] = str(e)
        finally:
            st["running"] = False; st["state"] = "done"; st["ended"] = _t.time()''', '''        try:
            frames, polys, sec, err = sam2_propagate_objs(st["clip_full"], st["seeds"], step=st["step"], progress=st,
                                                          a=st.get("a"), b=st.get("b"), mode=st.get("mode"))
            st["nframes"] = len(frames); st["err"] = err; st["sec"] = sec
            if frames and not err:                       # 서버가 바로 저장 → 브라우저가 떠나 있어도 결과가 남는다
                sam2_store_write(st["clip_full"], frames, [{"t": q["t"], "obj": q.get("obj", 1), "box": q.get("box")} for q in st["seeds"]], polys)
                st["saved"] = True
        except Exception as e:
            st["err"] = str(e)
        finally:
            st["running"] = False; st["state"] = "done"; st["ended"] = _t.time()
            with _PROP_LOCK:                             # 끝난 작업은 최근 50개만 남긴다
                done = [j for j, x in _PROP_JOBS.items() if x.get("state") == "done"]
                for j in done[:-50]:
                    _PROP_JOBS.pop(j, None)''')
rep('''def prop_job_start(clip, seeds, back, fwd, step):
    with _PROP_LOCK:
        for jid0, st0 in _PROP_JOBS.items():      # 같은 클립이 대기·진행 중이면 그 작업을 그대로 돌려준다(중복 실행 방지)
            if st0.get("clip") == Path(clip).stem and st0.get("state") in ("queued", "running"):
                return jid0
        _PROP_SEQ[0] += 1
        jid = str(_PROP_SEQ[0])
        st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "back": back, "fwd": fwd, "step": step,
                                "done": 0, "total": 0, "running": True, "state": "queued", "result": None, "err": None, "sec": 0, "saved": False}''', '''def prop_job_start(clip, seeds, a, b, step, mode=None):
    """전파 작업을 큐에 넣고 id 를 준다. 같은 클립이 이미 대기·진행 중이면 None(새 참조샷을 조용히 버리지 않는다)."""
    with _PROP_LOCK:
        for st0 in _PROP_JOBS.values():
            if st0.get("clip") == Path(clip).stem and st0.get("state") in ("queued", "running"):
                return None
        _PROP_SEQ[0] += 1
        jid = str(_PROP_SEQ[0])
        st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "a": a, "b": b, "step": step, "mode": mode,
                                "done": 0, "total": 0, "running": True, "state": "queued", "nframes": 0, "err": None, "sec": 0, "saved": False}''')
rep('''                    "err": st.get("err"), "saved": st.get("saved", False), "sec": st.get("sec", 0),
                    "nframes": len(st["result"]) if st.get("result") else 0})''', '''                    "err": st.get("err"), "saved": st.get("saved", False), "sec": st.get("sec", 0), "nframes": st.get("nframes", 0), "mode": st.get("mode")})''')
rep('''def sam2_store_clear(clip):
    f = SAM2_DIR / (Path(clip).stem + ".json")
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    n = len(d.get("frames") or {})
    d["frames"] = {}; d["seeds"] = []
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return n


def sam2_store_write(clip, frames, seeds):
    """전파 결과를 자동라벨/sam2/<클립>.json 에 합친다(같은 시각은 덮어쓴다). 씨앗 프레임도 기록."""
    SAM2_DIR.mkdir(parents=True, exist_ok=True)
    f = SAM2_DIR / (Path(clip).stem + ".json")
    d = {"clip": Path(clip).stem, "frames": {}, "seeds": []}
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    d.setdefault("frames", {}); d.setdefault("seeds", [])
    hand = _hand_box_frames(clip)                     # 손라벨 박스가 있는 프레임은 손라벨만(SAM 결과는 버린다)
    for t, objs in (frames or {}).items():
        k = f"{float(t):.1f}"; cur = d["frames"].get(k)
        if k in hand:
            continue
        d["frames"][k] = {**cur, **objs} if isinstance(cur, dict) and isinstance(objs, dict) else objs   # 같은 시각: 객체 단위 병합
    have = {(round(float(x.get("t", 0)), 2), int(x.get("obj", 1))) for x in d["seeds"]}
    for sd in seeds or []:
        k = (round(float(sd.get("t", 0)), 2), int(sd.get("obj", 1)))
        if k not in have:
            d["seeds"].append({"t": sd.get("t"), "obj": sd.get("obj", 1), "box": sd.get("box")}); have.add(k)
    d["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return len(d["frames"])


def _hand_box_frames(clip):
    """그 클립에서 손라벨 박스(cls>=0)가 있는 프레임 키("190.5") 집합. 사람·화재 손라벨 파일 둘 다 본다."""
    stem = Path(clip).stem; out = set()
    for fn in ("person_labels.json", "fire_labels.json"):
        fl = data_path("data/학습데이터/손라벨/" + fn, fn)
        try:
            rows = json.loads(fl.read_text(encoding="utf-8")) if fl.exists() else []
        except Exception:
            rows = []
        for r in rows:
            if Path(str(r.get("clip", ""))).stem == stem and int(r.get("cls", -1)) >= 0:
                out.add(f"{round(float(r.get('t', 0)) * 2) / 2:.1f}")
    return out


def sam2_store_drop(clip, t):
    f = SAM2_DIR / (Path(clip).stem + ".json")
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    k = f"{float(t):.1f}"
    n = 1 if k in (d.get("frames") or {}) else 0
    d["frames"].pop(k, None)
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return n
''', '''def _sam2_file(clip):
    return SAM2_DIR / (Path(clip).stem + ".json")


def _sam2_load(clip):
    d = read_json(_sam2_file(clip), {"clip": Path(clip).stem})
    d.setdefault("frames", {}); d.setdefault("polys", {}); d.setdefault("seeds", [])
    return d


def sam2_store_clear(clip):
    f = _sam2_file(clip)
    if not f.exists():
        return 0
    d = _sam2_load(clip)
    n = len(d["frames"])
    d["frames"] = {}; d["polys"] = {}; d["seeds"] = []
    write_json(f, d)
    return n


def sam2_store_write(clip, frames, seeds, polys=None):
    """전파 결과(박스·윤곽선)를 자동라벨/sam2/<클립>.json 에 합친다(같은 시각·같은 객체는 덮어쓴다). 참조샷도 기록.
    손라벨 박스가 있는 프레임은 손라벨만 쓰므로 건너뛴다."""
    d = _sam2_load(clip)
    hand = _hand_box_frames(clip)
    for t, objs in (frames or {}).items():
        k = tkey(t)
        if k in hand or not isinstance(objs, dict):
            continue
        d["frames"][k] = {**(d["frames"].get(k) or {}), **objs}
        if polys and polys.get(t):
            d["polys"][k] = {**(d["polys"].get(k) or {}), **polys[t]}
    have = {(round(float(x.get("t", 0)), 2), int(x.get("obj", 1))) for x in d["seeds"]}
    for sd in seeds or []:
        k = (round(float(sd.get("t", 0)), 2), int(sd.get("obj", 1)))
        if k not in have:
            d["seeds"].append({"t": sd.get("t"), "obj": sd.get("obj", 1), "box": sd.get("box")}); have.add(k)
    d["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(_sam2_file(clip), d)
    return len(d["frames"])


def _hand_box_frames(clip):
    """그 클립에서 손라벨 박스(cls>=0)가 있는 프레임 키 집합. 사람·화재 손라벨 파일 둘 다 본다."""
    stem = Path(clip).stem; out = set()
    for kind in ("person", "fire"):
        for r in read_json(label_file(kind), []):
            if Path(str(r.get("clip", ""))).stem == stem and int(r.get("cls", -1)) >= 0:
                out.add(tkey(r.get("t", 0)))
    return out


def sam2_store_drop(clip, t):
    f = _sam2_file(clip)
    if not f.exists():
        return 0
    d = _sam2_load(clip)
    k = tkey(t)
    n = 1 if k in d["frames"] else 0
    d["frames"].pop(k, None); d["polys"].pop(k, None)
    write_json(f, d)
    return n
''')

# ---------- 5. 라우트: 죽은 것 제거, 저장 경로 공통화, 새 엔드포인트(fuse_detect·config) ----------
for r_ in ("/api/sam2_save", "/api/sam2_propagate", "/api/autolabel_drop_obj", "/api/gtframes", "/api/sam2_progress",
           "/api/autolabel_bg", "/api/sam2_candidates", "/api/sam2", "/api/pseudolabel", "/api/labelmeta", "/api/newframes", "/api/clipstat", "/app.js"):
    cut_route(r_)
cut_between('''        m = re.match(r"/newframe/(.+\\.png)$", p)''', '''        m = re.match(r"/frame/(.+\\.png)$", p)''')
rep('''        if p == "/api/sam2_propagate_start":  # 전파를 백그라운드로 시작 → 작업 id. 진행률은 GET /api/sam2_progress?id=
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                jid = prop_job_start(b["clip"], b.get("seeds") or [], float(b.get("back", 5)), float(b.get("fwd", 10)), float(b.get("step", 0.5)))
                self._bytes(json.dumps({"id": jid}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return''', '''        if p == "/api/sam2_propagate_start":  # 전파를 큐에 넣는다 → 작업 id. 진행은 GET /api/sam2_jobs?clip= 로 본다
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                a = b.get("a"); bb = b.get("b")
                jid = prop_job_start(b["clip"], b.get("seeds") or [], None if a is None else float(a), None if bb is None else float(bb),
                                     float(b.get("step", 0.5)), b.get("mode") or None)
                if jid is None:
                    self._bytes(json.dumps({"err": "이 클립은 이미 전파 중입니다. 끝나면 다시 누르세요"}).encode(), "application/json; charset=utf-8"); return
                self._bytes(json.dumps({"id": jid}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/fuse_detect":          # 화재 한 프레임: Grounding DINO 불·연기 박스 → SAM2 마스크
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                objs = fuse_detect(b["clip"], float(b["t"]), float(b.get("th", 0.25)))
                self._bytes(json.dumps({"objs": objs}, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"objs": {}, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return''')
rep('''        if p == "/api/autolabel_drop":       # 자동라벨에서 그 프레임을 뺀다(검수 화면의 ×). 손라벨과 무관.
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                f = AUTOLABEL_DIR / (Path(body["clip"]).stem + ".json")
                d = json.loads(f.read_text(encoding="utf-8"))
                t = f"{float(body['t']):.1f}"
                if t in (d.get("frames") or {}):
                    d["frames"][t] = []          # 지우지 않고 '검출 없음'으로 둔다(다시 프리필되지 않게)
                    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(f)
                    _AUTOL.pop(str(f), None)
                self._bytes(json.dumps({"ok": True}).encode(), "application/json; charset=utf-8")''', '''        if p == "/api/autolabel_drop":       # DINO 자동라벨에서 그 프레임을 뺀다. 손라벨과 무관.
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                f = AUTOLABEL_DIR / (Path(body["clip"]).stem + ".json")
                with _SAVE_LOCK:
                    d = read_json(f, {"frames": {}})
                    t = tkey(body["t"])
                    if t in (d.get("frames") or {}):
                        d["frames"][t] = []          # 지우지 않고 '검출 없음'으로 둔다(다시 프리필되지 않게)
                        write_json(f, d); _AUTOL.pop(str(f), None)
                self._bytes(json.dumps({"ok": True}).encode(), "application/json; charset=utf-8")''')
rep('''                clip = Path(body["clip"]).stem
                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
                with _SAVE_LOCK:
                    if fl.exists():                       # 초기화 직전 상태를 시각 붙여 따로 남긴다(복구용)
                        bdir = fl.parent / "_backup"; bdir.mkdir(exist_ok=True)
                        shutil.copyfile(fl, bdir / f"{fl.stem}.{time.strftime('%Y%m%d_%H%M%S')}.reset_{clip}.json")
                    rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                    keep = [r for r in rows if r.get("clip") != clip]
                    removed = len(rows) - len(keep)
                    tmp = fl.with_suffix(f".json.tmp{os.getpid()}")
                    tmp.write_text(json.dumps(keep, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(fl)''', '''                clip = Path(body["clip"]).stem
                fl = label_file(body.get("kind"))
                with _SAVE_LOCK:
                    if fl.exists():                       # 초기화 직전 상태를 시각 붙여 따로 남긴다(복구용)
                        bdir = fl.parent / "_backup"; bdir.mkdir(exist_ok=True)
                        shutil.copyfile(fl, bdir / f"{fl.stem}.{time.strftime('%Y%m%d_%H%M%S')}.reset_{clip}.json")
                    rows = read_json(fl, [])
                    keep = [r for r in rows if r.get("clip") != clip]
                    removed = len(rows) - len(keep)
                    write_json(fl, keep)''')
rep('''                fn = "person_labels.json" if body.get("kind") == "person" else "fire_labels.json"
                fl = data_path("data/학습데이터/손라벨/" + fn, fn)
                _backup_labels(fl)
                rows = json.load(open(fl, encoding="utf-8")) if fl.exists() else []
                clip = body["clip"]''', '''                fl = label_file(body.get("kind"))
                _backup_labels(fl)
                rows = read_json(fl, [])
                clip = body["clip"]''')
rep('''                if not body.get("boxes") and body.get("kind") == "person":
                    # 박스 0개로 저장(사람이 다 지움) = '검토했고 객체 없음' 마커. 이래야 다시 의사라벨 프리필 안 된다
                    rows.append({"file": file, "clip": clip, "src": src, "t": t, "cls": -1,
                                 "x": 0, "y": 0, "w": 0, "h": 0, "W": W, "H": Hh, "crop": [0, 0, W, Hh]})
                tmp = fl.with_suffix(f".json.tmp{os.getpid()}")   # 다른 프로세스가 같은 임시이름을 쓰면 내용이 섞인다
                json.dump(rows, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
                tmp.replace(fl)
                try:''', '''                if not body.get("boxes"):
                    # 박스 0개로 저장(사람이 다 지움) = '검토했고 객체 없음' 마커(사람·화재 공통). 이래야 다시 DINO 프리필 안 된다
                    rows.append({"file": file, "clip": clip, "src": src, "t": t, "cls": -1,
                                 "x": 0, "y": 0, "w": 0, "h": 0, "W": W, "H": Hh, "crop": [0, 0, W, Hh]})
                write_json(fl, rows)
                try:''')
rep('''        if p == "/api/labels":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            fn = "person_labels.json" if (q.get("kind") or [""])[0] == "person" else "fire_labels.json"
            f = data_path("data/학습데이터/손라벨/" + fn, fn)
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self._bytes(b"[]", "application/json; charset=utf-8")
            return''', '''        if p == "/api/labels":
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = label_file((q.get("kind") or [""])[0])
            self._stream(f, "application/json; charset=utf-8") if f.exists() else self._bytes(b"[]", "application/json; charset=utf-8")
            return
        if p == "/api/config":                # 클라이언트가 알아야 하는 서버 기본값
            self._bytes(json.dumps({"prop_default": PROP_DEFAULT_MODE, "prop_thr": PROP_THR}).encode(), "application/json; charset=utf-8")
            return''')
rep('''        if p == "/api/gtlabel":              # 정답라벨 저장소(클립) {frames, points, events, actions}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = GT_DIR / (Path((q.get("clip") or [""])[0]).stem + ".json")
            d = {"frames": {}, "points": {}, "events": [], "actions": {}}
            if f.exists():
                try: d = json.loads(f.read_text(encoding="utf-8"))
                except Exception: pass
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return''', '''        if p == "/api/gtlabel":              # 정답라벨 저장소(클립) {frames, points, events, actions}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            d = read_json(GT_DIR / (Path((q.get("clip") or [""])[0]).stem + ".json"), {"frames": {}, "points": {}, "events": [], "actions": {}})
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return''')
rep('''        if p == "/api/sam2label":            # SAM 전파 결과 저장소(클립 전체) {frames: {t: {obj: [x,y,w,h]}}, seeds}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            f = SAM2_DIR / (Path((q.get("clip") or [""])[0]).stem + ".json")
            d = {"frames": {}, "seeds": []}
            if f.exists():
                try: d = json.loads(f.read_text(encoding="utf-8"))
                except Exception: pass
            self._bytes(json.dumps(d, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return''', '''        if p == "/api/sam2label":            # SAM 전파 결과 저장소(클립 전체) {frames: {t: {obj: [x,y,w,h]}}, polys: {t: {obj: 윤곽선}}, seeds}
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self._bytes(json.dumps(_sam2_load((q.get("clip") or [""])[0]), ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return''')
rep('''                for fj in SAM2_DIR.glob("*.json"):
                    try:
                        fr = json.loads(fj.read_text(encoding="utf-8")).get("frames") or {}
                        ts = sorted(float(k) for k, v in fr.items() if v)
                        if ts:
                            out[fj.stem] = ts
                    except Exception:
                        pass''', '''                for fj in SAM2_DIR.glob("*.json"):
                    ts = sorted(float(k) for k, v in (read_json(fj, {}).get("frames") or {}).items() if v)
                    if ts:
                        out[fj.stem] = ts''')

# 정리 검증: 지운 함수가 남아 있지 않은지
for gone in ("def person_boxes", "def gdino_boxes(", "def sam2_box(", "def sam2_propagate(", "def sam2_propagate_multi(", "def bg_dino_start", "def gdino_boxes_bgr", "_EMB_CACHE", "RAW_CLASS_NOTE", "SAM2_MIN_SCORE"):
    assert gone not in s, gone
io.open(p, "w", encoding="utf-8").write(s)
print("ok", len(s.splitlines()), "lines")
