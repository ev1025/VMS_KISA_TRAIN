# -*- coding: utf-8 -*-
"""헤더 'KISA 검수' 클릭 → 저장된 마지막 화면을 지우고 처음 화면으로."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/dashboard.html"
s = io.open(p, encoding="utf-8").read()
old = ' <div class="brand">KISA 검수</div>'
new = (' <div class="brand" title="처음 화면으로" style="cursor:pointer" '
       'onclick="try{localStorage.removeItem(\'kisa_last_view\')}catch(e){};location.href=\'/\'">KISA 검수</div>')
assert s.count(old) == 1, "brand 앵커 없음"
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
