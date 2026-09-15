# -*- coding: utf-8 -*-
"""전파를 서버 큐로: 여러 클립의 전파를 연달아 걸어두면 워커 한 개가 순서대로 처리하고, 끝나면 서버가 바로 SAM 저장소에 저장한다.
브라우저를 떠나도 이어진다. /api/sam2_jobs?clip= 로 상태(대기 순번·진행률) 조회. /api/sam2_clear 로 클립의 SAM 결과 일괄 삭제."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "_PROP_Q" not in s, "이미 적용됨"

def rep(old, new):
    global s
    assert s.count(old) == 1, old[:100]
    s = s.replace(old, new, 1)

rep('''def prop_job_start(clip, seeds, back, fwd, step):
    _PROP_SEQ[0] += 1
    jid = str(_PROP_SEQ[0])
    st = _PROP_JOBS[jid] = {"done": 0, "total": 0, "running": True, "result": None, "err": None, "sec": 0}

    def work():
        try:
            frames, sec, err = sam2_propagate_objs(clip, seeds, back=back, fwd=fwd, step=step, progress=st)
            st["result"] = frames; st["err"] = err; st["sec"] = sec
        except Exception as e:
            st["err"] = str(e)
        finally:
            st["running"] = False
    threading.Thread(target=work, daemon=True).start()
    return jid''',
'''_PROP_Q = []                     # 대기 중인 job id (순서대로)
_PROP_LOCK = threading.Lock()
_PROP_WORKER = [None]            # 워커 스레드 하나 (GPU 공유·메모리 때문에 전파는 한 번에 하나)


def _prop_worker():
    import time as _t
    while True:
        with _PROP_LOCK:
            if not _PROP_Q:
                _PROP_WORKER[0] = None
                return
            jid = _PROP_Q.pop(0)
        st = _PROP_JOBS[jid]
        st["state"] = "running"; st["running"] = True; st["started"] = _t.time()
        try:
            frames, sec, err = sam2_propagate_objs(st["clip_full"], st["seeds"], back=st["back"], fwd=st["fwd"], step=st["step"], progress=st)
            st["result"] = frames; st["err"] = err; st["sec"] = sec
            if frames and not err:                       # 서버가 바로 저장 → 브라우저가 떠나 있어도 결과가 남는다
                sam2_store_write(st["clip_full"], frames, [{"t": q["t"], "obj": q.get("obj", 1), "box": q["box"]} for q in st["seeds"]])
                st["saved"] = True
        except Exception as e:
            st["err"] = str(e)
        finally:
            st["running"] = False; st["state"] = "done"; st["ended"] = _t.time()


def prop_job_start(clip, seeds, back, fwd, step):
    _PROP_SEQ[0] += 1
    jid = str(_PROP_SEQ[0])
    st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "back": back, "fwd": fwd, "step": step,
                            "done": 0, "total": 0, "running": True, "state": "queued", "result": None, "err": None, "sec": 0, "saved": False}
    with _PROP_LOCK:
        _PROP_Q.append(jid)
        if _PROP_WORKER[0] is None or not _PROP_WORKER[0].is_alive():
            _PROP_WORKER[0] = threading.Thread(target=_prop_worker, daemon=True)
            _PROP_WORKER[0].start()
    return jid


def prop_jobs_view(stem=None):
    """클립(또는 전체) 전파 작업 목록: 대기 순번·진행률·오류. 결과 본문은 뺀다."""
    out = []
    with _PROP_LOCK:
        q = list(_PROP_Q)
    for jid, st in _PROP_JOBS.items():
        if stem and st.get("clip") != stem:
            continue
        out.append({"id": jid, "clip": st.get("clip"), "state": st.get("state", "done" if not st.get("running") else "running"),
                    "pos": (q.index(jid) + 1) if jid in q else 0, "done": st.get("done", 0), "total": st.get("total", 0),
                    "err": st.get("err"), "saved": st.get("saved", False), "sec": st.get("sec", 0),
                    "nframes": len(st["result"]) if st.get("result") else 0})
    return out


def sam2_store_clear(clip):
    f = SAM2_DIR / (Path(clip).stem + ".json")
    if not f.exists():
        return 0
    d = json.loads(f.read_text(encoding="utf-8"))
    n = len(d.get("frames") or {})
    d["frames"] = {}; d["seeds"] = []
    tmp = f.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8"); tmp.replace(f)
    return n''')

# GET: 작업 목록
rep('''        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)''',
'''        if p == "/api/sam2_jobs":            # 전파 작업 상태(클립별 또는 전체)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            stem = Path((q.get("clip") or [""])[0]).stem or None
            self._bytes(json.dumps(prop_jobs_view(stem)).encode(), "application/json; charset=utf-8")
            return
        if p == "/api/sam2frames":           # 모든 클립의 SAM 전파 프레임 시각 목록 {stem: [t,...]} (목록 배지용)''')

# POST: 일괄 삭제
rep('''        if p == "/api/sam2_drop":             # 검수 × : 그 프레임을 sam2 저장소에서 뺀다''',
'''        if p == "/api/sam2_clear":            # 전파 토글 해제: 그 클립의 SAM 결과(프레임·씨앗) 전부 제거
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                cnt = sam2_store_clear(b["clip"])
                self._bytes(json.dumps({"ok": True, "dropped": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_drop":             # 검수 × : 그 프레임을 sam2 저장소에서 뺀다''')
io.open(p, "w", encoding="utf-8").write(s)
print("server: 전파 큐·자동 저장·일괄 삭제")
