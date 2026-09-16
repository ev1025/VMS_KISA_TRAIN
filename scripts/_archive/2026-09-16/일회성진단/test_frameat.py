# -*- coding: utf-8 -*-
"""프레임 뽑기 자체 점검. 서버 venv 로 실행:
   /NHNHOME/WORKSPACE/26mss002_E3/vms/.venv/bin/python dash_v2/test_frameat.py
서버를 띄우지 않고 serve_kisa 의 함수만 불러 확인한다."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import serve_kisa as S

clips = sorted(p.stem for p in S.SRC.glob("*.mp4"))
assert clips, f"원본 클립이 없다: {S.SRC}"
clip = clips[0]

ci = S.clip_info(clip)
assert ci and ci["frames"] > 0 and ci["fps"] > 0, ci

mid = int(ci["dur"]) // 2          # 라벨 단위가 1초라 초로 뽑는다
jpg = S.read_frame(clip, mid)
assert jpg and jpg[:2] == b"\xff\xd8", "JPEG 이 아니다"

import cv2, numpy as np
im = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
assert im is not None and (im.shape[1], im.shape[0]) == (ci["W"], ci["H"]), (im.shape, ci)

# 다른 초를 달라고 했으면 그림도 달라야 한다 (seek 이 실제로 먹었는지)
other = S.read_frame(clip, min(mid + 2, int(ci["dur"])))
assert other and other != jpg, "다른 프레임인데 같은 그림이 나왔다"

# 클립 이름으로 서버 파일을 읽어가는 것은 막혀야 한다
for bad in ("../../etc/passwd", "a/b", "", "..."):
    assert S.clip_info(bad) is None, bad
    assert S.read_frame(bad, 0) is None, bad
assert S.clip_info("없는클립_zzz") is None

# 초당 1장 = 라벨 가능한 프레임 수
print(f"OK  clip={clip} {int(ci['dur'])}초(=라벨 가능 {int(ci['dur'])+1}장) fps={ci['fps']} {ci['W']}x{ci['H']} jpeg={len(jpg)}B")
