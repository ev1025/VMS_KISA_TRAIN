# 2026-09-17 보관

엠아르오 화재/연기 800GB 분할압축을 로컬 PC 에서 풀어 dataset_24k/48k 를 만들던 파이프라인이다.
경로가 전부 그 PC 기준(`D:\화재연기_원천데이터`, `C:\Users\...\fire_smoke_yolo`)이라 이 서버에서는
첫 줄부터 돌지 않았다. `dataset_24k` 도 이미 지웠다.

- `config.py` — 위 경로들의 중앙 설정. `model.py` 가 import 했지만 값은 `WORK` 하나만 쓰였고
  그마저 `Path(__file__).parent / "work"` 라 config 없이도 같은 값이 나온다.
- `01_build_manifest.py` · `02_subsample_split.py` · `04_convert_to_yolo.py` · `05_hn_mine.py`

이 서버의 학습 진입점은 `scripts/exp_queue.py` → `model.py train` 이고 `--data`·`--project` 를 항상 넘긴다.
남은 `scripts/data_prep/` 파일(07_augment_domains · make_r960 · merge_parts · mirror_to_nvme · patch_aihubshell)은
config 를 쓰지 않고 지금도 쓰는 도구라 그대로 뒀다.

## 함께 옮긴 것
- `03_extract_images.ps1` · `06_hn_extract.ps1` — 같은 사슬의 7-Zip 선택추출 단계.
  `C:\Program Files\7-Zip\7z.exe` 를 찾고 04·05 로 넘기라고 안내한다. 리눅스에서는 못 돈다.
