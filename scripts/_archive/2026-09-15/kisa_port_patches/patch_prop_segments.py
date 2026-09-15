# -*- coding: utf-8 -*-
"""전파를 '참조샷 사이 구간' 단위로 나눈다.
진단(E02_001 객체1): transformers SAM2 비디오는 시작 프레임의 참조만 쓰고 뒤 프레임에 넣어 둔 참조 박스는 무시했다
(67.5초 참조 박스 20,187px 인데 결과 마스크는 2,100px·다른 사람 위치). 그래서 참조샷을 많이 찍어도 첫 장만 효과가 있었다.
→ 객체별로 [구간 시작→첫 참조] 역방향, [참조k→참조k+1) 정방향, [마지막 참조→구간 끝] 정방향으로 세션을 나눠 매 구간의 시작 참조를 실제로 쓴다."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "참조샷 사이 구간" not in s
i = s.index("    # 그룹별 세션: 첫 참조 프레임이 같은 객체들은 한 세션에서 함께 전파한다")
j = s.index("    return out, round(time.time() - tic, 1), None", i)
assert 0 < i < j
new = '''    # 참조샷 사이 구간 단위 전파: 각 구간은 그 구간 시작 참조 박스 하나만 조건으로 두고 새 세션에서 돈다.
    # (transformers SAM2 비디오는 시작 프레임 이후에 넣어 둔 참조 박스를 실제로 쓰지 않아, 참조샷이 여러 장이어도 첫 장만 효과가 있었다)
    def fidx(t):
        return min(range(len(times)), key=lambda k: abs(times[k] - float(t)))
    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    out = {}
    if progress is not None:
        progress["total"] = len(frames) * len(by_obj); progress["done"] = 0

    def to_px(b):
        return [float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]

    def area_at(prof, tsec):
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

    def run_segment(oid, i0, i1, seed_i, box, prof, rev):
        """frames[i0..i1] 구간을 seed_i(구간 안 인덱스) 의 박스 하나로 조건 걸고 rev 방향으로 전파."""
        if i1 < i0:
            return
        sub = frames[i0:i1 + 1]
        sess = proc.init_video_session(video=sub, inference_device=dev, dtype=torch.float32)
        proc.add_inputs_to_inference_session(sess, frame_idx=seed_i - i0, obj_ids=[oid], input_boxes=[[to_px(box)]], original_size=(H, W))
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=seed_i - i0, reverse=rev):
            gi = i0 + int(r.frame_idx)
            if progress is not None:
                if progress.get("cancel"):
                    raise RuntimeError("cancelled")
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            sc = r.object_score_logits
            if sc is not None and float(sc.detach().flatten()[0]) <= 0:      # 대상 없음(가림·이탈)
                continue
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2:
                arr = arr[0]
            bb = _mask_bbox(arr)
            if bb is None:
                continue
            x1, y1, x2, y2 = bb
            area = (x2 - x1) * (y2 - y1)
            sa = area_at(prof, times[gi]) or area
            if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 3.0:     # 근처 참조 박스 대비 3배 넘게 커지거나 1/3 아래 = 흘러감
                continue
            out.setdefault(f"{times[gi]:.1f}", {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5),
                                                                 round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]
        del sess
        torch.cuda.empty_cache()

    with torch.no_grad():
        for oid in sorted(by_obj):
            sds = sorted(by_obj[oid], key=lambda sd: float(sd["t"]))
            prof = [(float(sd["t"]), float(sd["box"][2]) * W * float(sd["box"][3]) * H) for sd in sds]
            idxs = [fidx(sd["t"]) for sd in sds]
            # 1) 구간 시작 → 첫 참조 (역방향)
            run_segment(oid, 0, idxs[0], idxs[0], sds[0]["box"], prof, True)
            # 2) 참조 k → 참조 k+1 직전 (정방향), 마지막 참조 → 끝
            for k, sd in enumerate(sds):
                i0 = idxs[k]
                i1 = (idxs[k + 1] - 1) if k + 1 < len(sds) else (len(frames) - 1)
                if k + 1 < len(sds) and idxs[k + 1] == i0:    # 같은 프레임에 참조가 둘이면 뒤 것만
                    continue
                run_segment(oid, i0, max(i0, i1), i0, sd["box"], prof, False)
'''
s = s[:i] + new + s[j:]
io.open(p, "w", encoding="utf-8").write(s)
print("ok")
