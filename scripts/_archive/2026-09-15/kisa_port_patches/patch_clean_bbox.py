# -*- coding: utf-8 -*-
"""SAM 박스가 마스크 윤곽보다 커지던 것: 박스를 마스크 '전체 픽셀'로 잡아 멀리 튄 작은 조각(스펙클)까지 포함했다.
→ 연결 성분 중 가장 큰 것의 5% 이상인 조각만으로 박스를 잡는다(다리처럼 갈라진 큰 부분은 포함, 잡티는 제외).
탭(sam2_mask_pts)과 전파(collect) 둘 다 적용."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "_mask_bbox" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)

# 헬퍼: sam2_mask_pts 정의 앞에
rep('''def sam2_mask_pts(clip, sec, pts, box=None):''',
'''def _mask_bbox(m, min_frac=0.05, min_px=20):
    """이진 마스크의 박스. 잡티 제외: 연결 성분 중 가장 큰 성분 넓이의 min_frac 이상인 것만 모아 박스를 잡는다.
    반환 (x1, y1, x2, y2) 픽셀, 없으면 None."""
    import cv2, numpy as np
    m8 = (m > 0).astype("uint8")
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m8, connectivity=8)
    if n <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = int(areas.max())
    if big < min_px:
        return None
    keep = [i + 1 for i, a in enumerate(areas) if a >= max(min_px, big * min_frac)]
    sel = np.isin(lab, keep)
    ys, xs = np.nonzero(sel)
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def sam2_mask_pts(clip, sec, pts, box=None):''')

# 탭 박스
rep('''    m = masks[0].numpy().astype("uint8")
    ys, xs = m.nonzero()
    if len(xs) == 0:
        return None, None, score
    x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
    bx = [round(x1 / w0, 5), round(y1 / h0, 5), round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)]''',
'''    m = masks[0].numpy().astype("uint8")
    bb = _mask_bbox(m)                                    # 잡티를 뺀 박스(윤곽선과 맞게)
    if bb is None:
        return None, None, score
    x1, y1, x2, y2 = bb
    bx = [round(x1 / w0, 5), round(y1 / h0, 5), round((x2 - x1) / w0, 5), round((y2 - y1) / h0, 5)]''')

# 전파 박스
rep('''                ys, xs = np.nonzero(arr[k] > 0)
                if len(xs) < 20:
                    continue
                x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
                area = (x2 - x1) * (y2 - y1); sa = seed_area.get(oid, area)''',
'''                bb = _mask_bbox(arr[k])                  # 잡티를 뺀 박스
                if bb is None:
                    continue
                x1, y1, x2, y2 = bb
                area = (x2 - x1) * (y2 - y1); sa = seed_area.get(oid, area)''')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
