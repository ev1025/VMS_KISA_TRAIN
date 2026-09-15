# -*- coding: utf-8 -*-
"""카테고리 전환 시 조건필터 레이스: 새 카테고리 조건(CONDS)이 도착하기 전에 이전 필터로 목록이 통째로 숨겨지고 복구 안 되던 것.
조건 도착 후 필터를 다시 적용한다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/js/data.js"
s = io.open(p, encoding="utf-8").read()
old = """      draw();
    }).catch(() => {});"""
new = """      draw(); applyCondFilter(box);              // 새 카테고리 조건이 도착했으니 필터를 다시 적용(이전 카테고리 조건으로 숨겨진 항목 복구)
    }).catch(() => {});"""
assert s.count(old) == 1, "앵커 없음"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
