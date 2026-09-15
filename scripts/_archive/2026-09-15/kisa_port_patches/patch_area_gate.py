# -*- coding: utf-8 -*-
"""전파 박스 크기 게이트 수정: '참조 박스 중 최대 넓이' 기준(1/6~3배)이라 카메라 쪽으로 걸어오는 사람처럼 크기가 12배 변하는 객체는
멀리 있던 프레임이 전부 버려졌다(E02_001 객체1 결과 0프레임). → 그 시각에 가장 가까운 참조샷 두 개 사이를 보간한 넓이 기준으로 1/3~3배."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "seed_prof" not in s
def rep(old, new):
    global s
    assert s.count(old) == 1, (s.count(old), old[:100])
    s = s.replace(old, new, 1)
rep('''    def collect(sess, oids, start, rev, seed_area):''',
'''    def area_at(prof, tsec):
        """참조샷 (시각, 넓이) 목록에서 tsec 의 기준 넓이(선형 보간, 밖은 가장 가까운 값)."""
        if not prof:
            return None
        if tsec <= prof[0][0]:
            return prof[0][1]
        if tsec >= prof[-1][0]:
            return prof[-1][1]
        for (t0, a0), (t1, a1) in zip(prof, prof[1:]):
            if t0 <= tsec <= t1:
                w = (tsec - t0) / (t1 - t0) if t1 > t0 else 0.0
                return a0 + (a1 - a0) * w
        return prof[-1][1]

    def collect(sess, oids, start, rev, seed_prof):''')
rep('''                bb = _mask_bbox(arr[k])                  # 잡티를 뺀 박스
                if bb is None:
                    continue
                x1, y1, x2, y2 = bb
                area = (x2 - x1) * (y2 - y1); sa = seed_area.get(oid, area)
                if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 6.0:   # 참조 박스 대비 3배 넘게 커지거나 1/6 아래 = 흘러감
                    continue''',
'''                bb = _mask_bbox(arr[k])                  # 잡티를 뺀 박스
                if bb is None:
                    continue
                x1, y1, x2, y2 = bb
                area = (x2 - x1) * (y2 - y1)
                sa = area_at(seed_prof.get(oid), times[i]) or area   # 그 시각 근처 참조 박스 넓이(보간)
                if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 3.0:   # 근처 참조 박스 대비 3배 넘게 커지거나 1/3 아래 = 흘러감
                    continue''')
rep('''        seed_area = {oid: max(float(sd["box"][2]) * W * float(sd["box"][3]) * H for sd in by_obj[oid]) for oid in oids}
        start = min(by_frame)
        collect(sess, oids, start, False, seed_area)
        collect(sess, oids, start, True, seed_area)''',
'''        seed_prof = {oid: sorted((float(sd["t"]), float(sd["box"][2]) * W * float(sd["box"][3]) * H) for sd in by_obj[oid]) for oid in oids}   # 객체별 (시각, 참조 넓이)
        start = min(by_frame)
        collect(sess, oids, start, False, seed_prof)
        collect(sess, oids, start, True, seed_prof)''')
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
