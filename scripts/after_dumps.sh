#!/bin/bash
# 덤프 두 개가 끝나면 재현을 확인하고, 맞으면 검수 탭 메타를 새로 만든다.
#
# 왜 있나 (2026-09-16)
#   "덤프 끝나면 재현 확인하고 dash_meta 다시 만들기" 를 사람이 기억해야 했다.
#   오늘 문제의 상당수가 "사람이 상태를 추적해야 하는 구조" 에서 나왔다. 스스로 돌게 한다.
#
# 하는 일
#   1. person_redump(침입) 과 server_tdump(배회) 가 끝날 때까지 기다린다
#   2. 새 덤프로 재현이 실측과 맞는지 본다 (scripts/check_repro.py)
#   3. 맞으면 build_dash_meta.py 가 새 덤프를 읽게 하고 dash_meta.json 을 다시 만든다
#      안 맞으면 만들지 않는다. 틀린 신호를 화면에 올리면 안 된다.
#
# 결과는 logs/after_dumps.log 에 남는다.
set -u
cd /NHNHOME/WORKSPACE/26mss002_E3/vms
PY=.venv/bin/python
say() { echo "[$(TZ=Asia/Seoul date '+%m-%d %H:%M:%S')] $*"; }

say "덤프가 끝나기를 기다린다"
while pgrep -f 'person_redump.p[y]' >/dev/null || pgrep -f 'server_tdump.p[y]' >/dev/null; do
  sleep 60
done
say "덤프 종료 · 침입 $(ls dumps/intrusion_tile_v3 2>/dev/null | wc -l)편 · 배회 $(ls dumps/loiter_botsort_v2 2>/dev/null | wc -l)편"

# 새 덤프를 확인기가 먼저 보도록 후보 앞에 넣는다
$PY - <<'PYEOF'
from pathlib import Path
p = Path('scripts/check_repro.py'); s = p.read_text(encoding='utf-8')
s = s.replace('"배회": (["loiter_trk_id"]', '"배회": (["loiter_botsort_v2", "loiter_trk_id"]')
p.write_text(s, encoding='utf-8')
print('  확인기가 새 배회 덤프를 먼저 본다')
PYEOF

say "재현 확인"
$PY scripts/check_repro.py
RC=$?
say "check_repro 되돌아온 값 = $RC"

if [ "$RC" -ne 0 ]; then
  say "재현이 아직 안 맞는다. dash_meta.json 은 만들지 않는다(틀린 신호를 화면에 올리면 안 된다)."
  say "끝"
  exit 1
fi

say "재현이 맞는다 · build_dash_meta 가 새 덤프를 읽게 바꾼다"
$PY - <<'PYEOF'
from pathlib import Path
p = Path('dash_v2/build_dash_meta.py'); s = p.read_text(encoding='utf-8')
s = s.replace('G/"dumps/intrusion_tile"', 'G/"dumps/intrusion_tile_v3"')
s = s.replace('G/"dumps/loiter_trk_id"', 'G/"dumps/loiter_botsort_v2"')
p.write_text(s, encoding='utf-8')
print('  덤프 경로 교체 완료')
PYEOF

say "dash_meta.json 재생성"
cp dash_v2/dash_meta.json dash_v2/dash_meta.json.bak 2>/dev/null
$PY dash_v2/build_dash_meta.py && say "완료 · 검수 탭과 결과 탭이 같은 값을 말한다" || {
  say "실패 · 예전 파일로 되돌린다"
  mv dash_v2/dash_meta.json.bak dash_v2/dash_meta.json 2>/dev/null
}
say "끝"
