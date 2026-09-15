# -*- coding: utf-8 -*-
"""확대창 프레임 이동 시 이미지가 한 템포 늦던 것:
 1) 새 이미지를 미리 받아 로드된 뒤 박스와 함께 바꿈(박스만 먼저 뜨는 어긋남 제거)
 2) 앞뒤 2프레임씩 원본 크기 이미지를 미리 받아 둠
 3) 격자를 열 때 전체 프레임의 원본 크기 캐시를 서버에서 순차로 만들어 둠(뒤에서)"""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/editor.js"
s = io.open(p, encoding="utf-8").read()
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep("""  const show = i => {
    idx = Math.min(Math.max(i, 0), items.length - 1);
    const d = cur();
    im.src = "/frameat?clip=" + encodeURIComponent(f.clip) + "&t=" + d.t;
    boxes = (d.boxes || []).map(b => b.slice());
    render();
  };""",
    """  const srcOf = t => "/frameat?clip=" + encodeURIComponent(f.clip) + "&t=" + t;
  const _pre = {};                                     // 미리 받아둔 이미지
  const preload = t => { const u = srcOf(t); if (_pre[u]) return _pre[u]; const g = new Image(); g.src = u; _pre[u] = g; return g; };
  let showSeq = 0;
  const show = i => {
    idx = Math.min(Math.max(i, 0), items.length - 1);
    const d = cur(); const my = ++showSeq;
    const g = preload(d.t);
    const apply = () => { if (my !== showSeq) return; im.src = g.src; boxes = (d.boxes || []).map(b => b.slice()); render(); };
    if (g.complete && g.naturalWidth) apply(); else { g.onload = apply; g.onerror = apply; }   // 이미지가 준비된 뒤 박스와 함께 바꾼다
    [1, 2, -1, -2].forEach(k => { const q = items[idx + k]; if (q) preload(q.t); });        // 앞뒤 프레임 미리 받기
  };""")
rep("""  try { await fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsFirst); } catch (e) {}   // 처음 보이는 장만 기다린다
  if (tsRest) fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsRest).catch(() => {});   // 나머지는 뒤에서
  fetch("/api/warmframes?w=0&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsFirst).catch(() => {});""",
    """  try { await fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsFirst); } catch (e) {}   // 처음 보이는 장만 기다린다
  if (tsRest) fetch("/api/warmframes?w=320&clip=" + encodeURIComponent(f.clip) + "&ts=" + tsRest).catch(() => {});   // 나머지는 뒤에서
  fetch("/api/warmframes?w=0&clip=" + encodeURIComponent(f.clip) + "&ts=" + items.map(d => d.t).join(",")).catch(() => {});   // 확대창용 원본 크기도 전부 뒤에서 캐시""")
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
