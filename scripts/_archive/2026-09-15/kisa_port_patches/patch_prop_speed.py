# -*- coding: utf-8 -*-
"""전파 속도·중복
1) 같은 첫 참조 프레임을 가진 객체들은 한 세션에서 함께 전파(객체 수만큼 걸리던 시간을 그룹 수만큼으로). 실패하면 그 그룹만 객체별로 재시도.
2) 같은 클립에 대기·진행 중인 전파가 있으면 새 작업을 만들지 않고 그 작업 id 를 돌려준다(돌아와서 다시 눌러 두 번 도는 것 방지)."""
import io, re
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "그룹별 세션" not in s, "이미 적용됨"

# ---- 1) 그룹 세션
i = s.find("    # 객체별 세션: 객체마다 자기 참조샷만 조건 프레임으로 두고 따로 전파한다")
j = s.find("    return out, round(time.time() - tic, 1), None", i)
assert 0 < i < j
new = '''    # 그룹별 세션: 첫 참조 프레임이 같은 객체들은 한 세션에서 함께 전파한다(프레임당 비용은 객체 수와 거의 무관).
    # 첫 참조 프레임이 다른 객체를 한 세션에 넣으면 transformers SAM2 가 조건 출력이 없다며 죽으므로 그룹을 나눈다.
    def fidx(t):
        return min(range(len(times)), key=lambda k: abs(times[k] - float(t)))
    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    groups = {}                                   # 첫 참조 프레임 idx → [obj,...]
    for oid, sds in by_obj.items():
        groups.setdefault(min(fidx(sd["t"]) for sd in sds), []).append(oid)
    out = {}
    if progress is not None:
        progress["total"] = len(frames) * len(groups); progress["done"] = 0

    def to_px(b):
        return [float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]

    def collect(sess, oids, start, rev, seed_area):
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=start, reverse=rev):
            i = int(r.frame_idx)
            if progress is not None:
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            got = [int(o) for o in (r.object_ids if r.object_ids is not None else oids)]
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            if arr.ndim == 4:
                arr = arr[:, 0]
            if arr.ndim == 2:
                arr = arr[None]
            sc = r.object_score_logits
            scs = None if sc is None else sc.detach().flatten().tolist()
            for k, oid in enumerate(got):
                if k >= arr.shape[0]:
                    break
                if scs is not None and k < len(scs) and scs[k] <= 0:   # 대상 없음(가림·이탈)
                    continue
                ys, xs = np.nonzero(arr[k] > 0)
                if len(xs) < 20:
                    continue
                x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
                area = (x2 - x1) * (y2 - y1); sa = seed_area.get(oid, area)
                if area > 0.5 * W * H or area > 3.0 * sa or area < sa / 6.0:   # 참조 박스 대비 3배 넘게 커지거나 1/6 아래 = 흘러감
                    continue
                out.setdefault(f"{times[i]:.1f}", {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5),
                                                                    round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]

    def run_group(oids):
        sess = proc.init_video_session(video=frames, inference_device=dev, dtype=torch.float32)
        by_frame = {}                             # 같은 프레임의 객체들은 한 번에 넣어야 한다
        for oid in oids:
            for sd in by_obj[oid]:
                by_frame.setdefault(fidx(sd["t"]), {})[oid] = to_px(sd["box"])
        for si in sorted(by_frame):
            os_ = sorted(by_frame[si])
            proc.add_inputs_to_inference_session(sess, frame_idx=si, obj_ids=os_,
                                                 input_boxes=[[by_frame[si][o] for o in os_]], original_size=(H, W))
        seed_area = {oid: max(float(sd["box"][2]) * W * float(sd["box"][3]) * H for sd in by_obj[oid]) for oid in oids}
        start = min(by_frame)
        collect(sess, oids, start, False, seed_area)
        collect(sess, oids, start, True, seed_area)
        del sess
        torch.cuda.empty_cache()

    with torch.no_grad():
        for start_idx, oids in sorted(groups.items()):
            try:
                run_group(sorted(oids))
            except Exception as e:                # 그룹 전파가 죽으면 그 그룹만 객체별로 다시(한 객체씩은 항상 된다)
                if len(oids) == 1:
                    raise
                if progress is not None:
                    progress["total"] += len(frames) * (len(oids) - 1)
                for oid in sorted(oids):
                    run_group([oid])
'''
s = s[:i] + new + s[j:]

# ---- 2) 같은 클립 중복 작업 방지
old = '''def prop_job_start(clip, seeds, back, fwd, step):
    with _PROP_LOCK:
        _PROP_SEQ[0] += 1'''
new2 = '''def prop_job_start(clip, seeds, back, fwd, step):
    with _PROP_LOCK:
        for jid0, st0 in _PROP_JOBS.items():      # 같은 클립이 대기·진행 중이면 그 작업을 그대로 돌려준다(중복 실행 방지)
            if st0.get("clip") == Path(clip).stem and st0.get("state") in ("queued", "running"):
                return jid0
        _PROP_SEQ[0] += 1'''
assert s.count(old) == 1
s = s.replace(old, new2, 1)
io.open(p, "w", encoding="utf-8").write(s)
print("serve_kisa.py: 그룹 세션 · 중복 방지")
