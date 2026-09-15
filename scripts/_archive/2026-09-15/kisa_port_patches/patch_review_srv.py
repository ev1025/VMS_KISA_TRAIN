# -*- coding: utf-8 -*-
"""리뷰 결함 수정(서버)
5) _PROP_JOBS 삽입·순회를 락 안에서
6) sam2 저장소 read-modify-write 세 함수에 _SAVE_LOCK
7) 같은 시각 프레임은 객체 단위로 병합(다른 객체의 이전 결과 보존)"""
import io, re
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "_locked_store" not in s, "이미 적용됨"
def rep(old, new, cnt=1):
    global s
    assert s.count(old) == cnt, (s.count(old), old[:100])
    s = s.replace(old, new)

# 5) 잡 사전 락
rep('''def prop_job_start(clip, seeds, back, fwd, step):
    _PROP_SEQ[0] += 1
    jid = str(_PROP_SEQ[0])
    st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "back": back, "fwd": fwd, "step": step,
                            "done": 0, "total": 0, "running": True, "state": "queued", "result": None, "err": None, "sec": 0, "saved": False}
    with _PROP_LOCK:
        _PROP_Q.append(jid)''',
'''def prop_job_start(clip, seeds, back, fwd, step):
    with _PROP_LOCK:
        _PROP_SEQ[0] += 1
        jid = str(_PROP_SEQ[0])
        st = _PROP_JOBS[jid] = {"id": jid, "clip": Path(clip).stem, "clip_full": clip, "seeds": seeds, "back": back, "fwd": fwd, "step": step,
                                "done": 0, "total": 0, "running": True, "state": "queued", "result": None, "err": None, "sec": 0, "saved": False}
        _PROP_Q.append(jid)''')
rep('''    out = []
    with _PROP_LOCK:
        q = list(_PROP_Q)
    for jid, st in _PROP_JOBS.items():''',
'''    out = []
    with _PROP_LOCK:
        q = list(_PROP_Q); items = list(_PROP_JOBS.items())   # 스냅샷 뒤 순회(순회 중 삽입 방지)
    for jid, st in items:''')

# 7) 객체 단위 병합
rep('''    for t, objs in (frames or {}).items():
        d["frames"][f"{float(t):.1f}"] = objs''',
'''    for t, objs in (frames or {}).items():
        k = f"{float(t):.1f}"; cur = d["frames"].get(k)
        d["frames"][k] = {**cur, **objs} if isinstance(cur, dict) and isinstance(objs, dict) else objs   # 같은 시각: 객체 단위 병합''')

# 6) 저장소 함수 락: sam2_store_drop 정의 끝 뒤에 래핑
m = re.search(r"\ndef sam2_store_drop\(clip, t\):\n(?:.*\n)*?    return n\n", s)
assert m, "sam2_store_drop 끝을 못 찾음"
wrap = '''

def _locked_store(fn):
    """sam2 저장소는 read-modify-write. 전파 워커·검수 ×·일괄 삭제가 겹쳐도 한쪽이 사라지지 않게 savelabel 과 같은 락을 쓴다."""
    def w(*a, **k):
        with _SAVE_LOCK:
            return fn(*a, **k)
    w.__name__ = fn.__name__
    return w


sam2_store_write = _locked_store(sam2_store_write)
sam2_store_drop = _locked_store(sam2_store_drop)
sam2_store_clear = _locked_store(sam2_store_clear)
'''
s = s[:m.end()] + wrap + s[m.end():]
assert s.index("def sam2_store_write") < s.index("sam2_store_write = _locked_store") and s.index("def sam2_store_clear") < s.index("sam2_store_clear = _locked_store")
io.open(p, "w", encoding="utf-8").write(s)
print("serve_kisa.py: 리뷰 수정 3건")
