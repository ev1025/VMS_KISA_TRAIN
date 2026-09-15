# -*- coding: utf-8 -*-
"""전파를 객체별 세션으로 나눈다.
원인: 객체 A 는 10초, 객체 B 는 20초에만 참조샷이 있으면 한 세션에서 10초부터 전파할 때 B 의 조건 프레임 출력이 없어
transformers SAM2 가 'maskmem_features in conditioning outputs cannot be empty' 로 죽는다(공식 구현도 같은 제약).
객체마다 자기 참조샷만 조건으로 두고 따로 전파하면 문제가 없다. 프레임은 한 번만 읽어 재사용."""
import io
p = "/NHNHOME/WORKSPACE/26mss002_E3/vms/dash_v2/serve_kisa.py"
s = io.open(p, encoding="utf-8").read()
assert "객체별 세션" not in s, "이미 적용됨"
d = s.find("def sam2_propagate_objs(")
assert d > 0
i = s.find("    sess = proc.init_video_session(video=frames, inference_device=dev, dtype=torch.float32)", d)
j = s.find("    return out, round(time.time() - tic, 1), None", i)
assert 0 < d < i < j
assert "\ndef " not in s[d + 10:j], "함수 경계를 넘었다"
new = '''    # 객체별 세션: 객체마다 자기 참조샷만 조건 프레임으로 두고 따로 전파한다(서로 다른 프레임에 찍힌 객체들이 한 세션에 있으면 죽는다)
    by_obj = {}
    for sd in seeds:
        by_obj.setdefault(int(sd.get("obj", 1)), []).append(sd)
    out = {}
    if progress is not None:
        progress["total"] = len(frames) * len(by_obj); progress["done"] = 0

    def collect(sess, oid, start, rev):
        for r in model.propagate_in_video_iterator(sess, start_frame_idx=start, reverse=rev):
            i = int(r.frame_idx)
            if progress is not None:
                progress["done"] = min(progress.get("done", 0) + 1, progress["total"])
            m = proc.post_process_masks(r.pred_masks.unsqueeze(0).cpu().float(), [(H, W)], binarize=True)[0]
            arr = np.asarray(m.numpy() if hasattr(m, "numpy") else m)
            while arr.ndim > 2:                 # (1,1,H,W)/(1,H,W) → (H,W). 세션에 객체가 하나라 첫 장이 그 객체
                arr = arr[0]
            ys, xs = np.nonzero(arr > 0)
            if len(xs) < 20:
                continue
            x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
            if (x2 - x1) * (y2 - y1) > 0.5 * W * H:
                continue
            out.setdefault(f"{times[i]:.1f}", {})[str(oid)] = [round(x1 / W, 5), round(y1 / H, 5),
                                                                round((x2 - x1) / W, 5), round((y2 - y1) / H, 5)]

    with torch.no_grad():
        for oid, sds in sorted(by_obj.items()):
            sess = proc.init_video_session(video=frames, inference_device=dev, dtype=torch.float32)
            idxs = []
            for sd in sds:                      # 같은 객체의 참조샷이 여러 프레임이면 전부 조건 프레임
                si = min(range(len(times)), key=lambda k: abs(times[k] - float(sd["t"])))
                b = sd["box"]
                bx = [float(b[0]) * W, float(b[1]) * H, (float(b[0]) + float(b[2])) * W, (float(b[1]) + float(b[3])) * H]
                proc.add_inputs_to_inference_session(sess, frame_idx=si, obj_ids=[oid], input_boxes=[[bx]], original_size=(H, W))
                idxs.append(si)
            collect(sess, oid, min(idxs), False)
            collect(sess, oid, min(idxs), True)
            del sess
            torch.cuda.empty_cache()
'''
s = s[:i] + new + s[j:]
io.open(p, "w", encoding="utf-8").write(s)
print("serve_kisa.py: 객체별 전파")
