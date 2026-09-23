# 배포 가중치의 원본 (2026-09-23)

시험장에서 도는 `VMS_KISA/weights/kisa/*.pt` 가 **어느 학습에서 나왔는지** 를 잃지 않으려고 모아 둔다.

`fire_small.pt` 의 원본이 `logs/_archive/2026-09-15/r960오염실험/` 안에만 있었다.
폴더 이름이 '오염실험' 이라 나중에 정리하다 지울 위험이 있어 여기로 옮겼다.

## 들어 있는 것

| 파일 | 배포 이름 | 나온 실험 | 가중치 서명 |
| :-- | :-- | :-- | :-- |
| `fire_fog_fresh_48k_wildall_20260909_best.pt` | `fire_fog.pt` @640 | `fresh_48k_wildall_20260909` | `613ed444dcf7` |
| `fire_small_s2_s960_20260913_best.pt` | `fire_small.pt` @960 | `s2_s960_20260913` | `6a1a69fe0511` |

서명은 state_dict 를 정렬해 이어 붙인 md5 앞 12자리다. 2026-09-23 에 배포본과 대조해 일치를 확인했다.

```
확인 방법
  python - <<'EOF'
  import torch, hashlib
  d = torch.load("<파일>", map_location="cpu", weights_only=False)
  m = d["model"] if isinstance(d, dict) and "model" in d else d
  sd = m.state_dict() if hasattr(m, "state_dict") else m
  h = hashlib.md5()
  for k in sorted(sd):
      v = sd[k]
      if hasattr(v, "detach"):
          h.update(v.detach().float().cpu().numpy().tobytes())
  print(h.hexdigest()[:12])
  EOF
```

## 알아야 할 것

**`fire_fog` 는 채점셋을 학습했다.** `oversample: {human_fire: 5}` 인데 `human_fire` 안에
채점 10편의 라벨된 프레임 2,520장이 들어 있다(`C00_012_0007` 600장 · `C00_216_0003` 590장 등).
그래서 `results/BASELINE.json` 의 방화 100.00 은 자기가 학습한 영상으로 잰 값이다.
LOOCV 80.00 도 선택 편향만 잡지 학습 유출은 못 잡는다.

정직한 기준선은 `f960_mask_hn_x2_fog3_20260920` 이다. 배포 규칙으로 73.68,
채점 10편에 규칙을 맞추면 94.74 다. 100.00 과의 차이가 유출분이다.

**`fire_small` 은 데이터가 깨끗하다.** `oversample: {handset_fire_hn: 4}` 로 채점셋이 없다.
다만 `runs/s2_s960_20260913/yolo11s/weights/` 에 있는 파일은 2026-09-15 재학습 실패가
덮어쓴 잔해라 **읽히지도 않는다.** 그쪽을 쓰면 안 된다.

## 사람 가중치는 여기 없다

`person_v2.pt` · `person_v3.pt` 는 학습 데이터의 57%가 의사라벨이었고 그 데이터셋이
삭제돼 **재현이 안 된다**(`docs/미검원인.md`). 원본 가중치는 `VMS_KISA` 저장소에만 있다.
채점셋 누수는 없다(학습셋 8곳 전수 검사 0건).
