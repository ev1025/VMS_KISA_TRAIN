# -*- coding: utf-8 -*-
"""원본 데이터 목록을 다시 그릴 때(탭 전환·복귀) 첫 영상 대신 마지막에 보던 영상을 연다(목록에 있으면)."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/data.js"
s = io.open(p, encoding="utf-8").read()
old = """    if (!r.images.length) openClip(r.videos[0]);"""
new = """    if (!r.images.length) {
      let last = null; try { last = (loadSession() || {}).rel; } catch (e) {}
      openClip(last && r.videos.includes(last) ? last : r.videos[0]);   // 마지막에 보던 영상이 이 목록에 있으면 그걸로
    }"""
assert s.count(old) == 1, "앵커 없음"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
