# -*- coding: utf-8 -*-
"""전파 취소: 진행·대기 중에 [전파 취소] 를 누르면 그 클립의 작업을 중단한다(대기는 큐에서 빼고, 진행 중은 다음 프레임에서 멈춤·저장 안 함)."""
import io
V = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/"
def patch(name, pairs):
    p = V + name; s = io.open(p, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (name, s.count(old), old[:90])
        s = s.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8").write(s); print(name, "ok")

patch("serve_kisa.py", [
    # collect 루프에서 취소 확인
    ("""        for r in model.propagate_in_video_iterator(sess, start_frame_idx=start, reverse=rev):
            i = int(r.frame_idx)
            if progress is not None:
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            got = [int(o) for o in (r.object_ids if r.object_ids is not None else oids)]""",
     """        for r in model.propagate_in_video_iterator(sess, start_frame_idx=start, reverse=rev):
            i = int(r.frame_idx)
            if progress is not None:
                if progress.get("cancel"):
                    raise RuntimeError("cancelled")
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            got = [int(o) for o in (r.object_ids if r.object_ids is not None else oids)]"""),
    # 워커: 취소된 작업은 건너뜀, 취소 오류는 저장 안 함
    ("""        st = _PROP_JOBS[jid]
        st["state"] = "running"; st["running"] = True; st["started"] = _t.time()""",
     """        st = _PROP_JOBS[jid]
        if st.get("cancel"):
            st["state"] = "done"; st["running"] = False; st["err"] = "cancelled"; continue
        st["state"] = "running"; st["running"] = True; st["started"] = _t.time()"""),
    # 취소 API
    ("""        if p == "/api/sam2_clear":            # 전파 토글 해제: 그 클립의 SAM 결과(프레임·씨앗) 전부 제거""",
     """        if p == "/api/sam2_cancel":           # 이 클립의 대기·진행 중 전파 취소
            try:
                n = int(self.headers.get("Content-Length", 0))
                b = json.loads(self.rfile.read(n) or b"{}")
                stem = Path(b["clip"]).stem; cnt = 0
                with _PROP_LOCK:
                    for jid0, st0 in _PROP_JOBS.items():
                        if st0.get("clip") == stem and st0.get("state") in ("queued", "running"):
                            st0["cancel"] = True; cnt += 1
                            if jid0 in _PROP_Q:
                                _PROP_Q.remove(jid0); st0["state"] = "done"; st0["running"] = False; st0["err"] = "cancelled"
                self._bytes(json.dumps({"ok": True, "cancelled": cnt}).encode(), "application/json; charset=utf-8")
            except Exception as e:
                self._bytes(json.dumps({"ok": False, "err": str(e)}).encode(), "application/json; charset=utf-8", 500)
            return
        if p == "/api/sam2_clear":            # 전파 토글 해제: 그 클립의 SAM 결과(프레임·씨앗) 전부 제거"""),
])

patch("js/editor.js", [
    # 진행 중엔 버튼이 '전파 취소' 로, 눌리면 취소
    ("""  let _watching = false;
  const watchJob = async () => {                      // 이 클립의 전파 작업을 끝날 때까지 지켜본다(다른 클립에 가 있어도 계속)
    if (_watching) return; _watching = true;
    let seen = null;""",
     """  let _watching = false, _activeJob = null;
  const watchJob = async () => {                      // 이 클립의 전파 작업을 끝날 때까지 지켜본다(다른 클립에 가 있어도 계속)
    if (_watching) return; _watching = true;
    let seen = null;"""),
    ("""      if (!act) { if (seen) seen = jobs.find(jb => jb.id === seen.id) || seen; break; }
      seen = act;""",
     """      if (!act) { _activeJob = null; if (seen) seen = jobs.find(jb => jb.id === seen.id) || seen; break; }
      seen = act; _activeJob = act;"""),
    ("""      if (ED && ED._tok === MY) { rowObj.style.pointerEvents = "none"; rowObj.style.opacity = "0.5"; bHand.disabled = true; bHand.style.opacity = "0.4"; bGo.disabled = true; pstat.innerHTML = act.state === "queued" ?""",
     """      if (ED && ED._tok === MY) { rowObj.style.pointerEvents = "none"; rowObj.style.opacity = "0.5"; bHand.disabled = true; bHand.style.opacity = "0.4"; bGo.disabled = false; bGo.textContent = "전파 취소"; pstat.innerHTML = act.state === "queued" ?"""),
    ("""    if (ED && ED._tok === MY) { rowObj.style.pointerEvents = ""; rowObj.style.opacity = ""; bHand.disabled = false; bHand.style.opacity = ""; bGo.disabled = false; pstat.innerHTML = seen.err ? '<b style="color:#f85149">실패</b>' : ""; }
    if (!seen.err) {""",
     """    if (ED && ED._tok === MY) { rowObj.style.pointerEvents = ""; rowObj.style.opacity = ""; bHand.disabled = false; bHand.style.opacity = ""; bGo.disabled = false; bGo.textContent = "전파"; pstat.innerHTML = seen.err === "cancelled" ? '<span style="color:var(--mut)">취소됨</span>' : seen.err ? '<b style="color:#f85149">실패</b>' : ""; if (seen.err) setTimeout(() => { if (ED && ED._tok === MY) pstat.innerHTML = ""; }, 3000); }
    if (!seen.err) {"""),
    ("""  bGo.onclick = async () => {
    if (SM.propFrames && SM.propFrames.length) {      // 토글 해제: 이 클립의 SAM 결과를 저장소에서 전부 뺀다""",
     """  bGo.onclick = async () => {
    if (_activeJob) {                                 // 진행·대기 중 → 취소(참조샷은 그대로 남아 다시 누르면 재전파)
      bGo.disabled = true;
      await fetch("/api/sam2_cancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ clip: f.clip }) }).catch(() => {});
      return;
    }
    if (SM.propFrames && SM.propFrames.length) {      // 토글 해제: 이 클립의 SAM 결과를 저장소에서 전부 뺀다"""),
])
