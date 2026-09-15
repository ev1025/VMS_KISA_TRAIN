# 서버 학습 (GPU 서버)

로컬에서 데이터셋(`data_prep/` 01~04)을 만든 뒤, 데이터셋(~7.8GB)만 서버로 보내 학습한다.
원본 800GB는 로컬에만 두고 옮기지 않는다.

## 1) 서버 환경 (1회)

```bash
cd $ROOT                       # 예: /workspace/data2/jinwoolee/yolo_fire_smoke
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
# 최신 카드는 cu128 필요 (cu124 이하 불가)
./.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
./.venv/bin/pip install -r requirements.txt
./.venv/bin/yolo checks
```

## 2) 데이터 전송 (로컬 Git Bash, 중간 tar 없이 스트리밍)

```bash
tar -C <DATA_HOME> -cf - dataset_24k | ssh <SERVER> "tar -C $ROOT -xf -"
```

`$ROOT/data.yaml` 은 서버 경로로 직접 작성한다.

```yaml
path: /workspace/data2/jinwoolee/yolo_fire_smoke/dataset
train: images/train
val: images/val
nc: 2
names: [fire, smoke]
```

## 3) 학습 · 평가 · 변환 (전부 model.py)

```bash
nohup ./.venv/bin/python model.py train --models yolov8s \
  --data $ROOT/data.yaml --project $ROOT/runs --device 2,3 --batch 32 --imgsz 640 \
  > train.log 2>&1 &

./.venv/bin/python model.py eval --weights $ROOT/runs/yolov8s/weights/best.pt --data $ROOT/data.yaml --device 2
./.venv/bin/python model.py export $ROOT/runs/yolov8s/weights/best.pt --static   # 엣지(HEF)용 정적 onnx
```

## 4) 회수 (로컬)

```bash
scp <SERVER>:$ROOT/runs/yolov8s/weights/best.pt work/runs/yolov8s/weights/
```

## 주의

- **GPU는 할당된 번호만 사용.** Ultralytics는 `device=`로 직접 잡으므로 `CUDA_VISIBLE_DEVICES`가 아니라 `--device 2,3`으로 지정.
- 사용 전 `nvidia-smi`로 타 사용자 점유 확인, 본인 프로세스만 종료.
- `--project`는 절대경로로. 상대경로면 ultralytics settings의 `runs_dir` 하위(홈 등)에 저장된다.
- DDP(다중 GPU)는 `--batch` 고정값 필요(AutoBatch `-1` 불가). HPO(`tune`)는 단일 GPU에서만 pruning 동작.
