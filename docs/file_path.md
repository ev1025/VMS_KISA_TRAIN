

# 파일 배치 및 경로 규칙 (file_path.md)

새 파일을 생성하거나 경로 및 상수를 다룰 때 반드시 준수해야 할 규칙입니다.



## 1. 경로·상수 하드코딩 금지

모든 공용 경로와 채점 상수는 `scripts/kisa_paths.py` 한 곳에만 정의하고 사용합니다.

```python
import kisa_paths as KP          # scripts/ 안에서 실행 시 import

KP.V                # 저장소 루트 (VMS_ROOT 환경변수로 오버라이드 가능)
KP.DEPLOY_VAL       # 배포 검증영상 폴더 (mp4와 GT xml 동위 배치)
KP.ZONE_MAPS        # 침입·배회 영역파일(.map)
KP.videos("방화")    # 항목별 영상 폴더 접근
KP.kisa_item("침입") # kisa_items.py 의 --item 값 ("intrusion")
KP.find_mp4(stem)   # 클립 이름으로 영상 찾기
KP.PERSON_ITEMS     # 사람 검출 모델이 점수에 영향을 주는 항목 (침입·배회)
KP.SAMPLE_STRIDE_S  # 채점 표본 간격 (0.5초)
KP.DEFAULT_IMGSZ    # 기본 입력 크기 (640)

```

### 절대 금지 사항

* 저장소 절대경로 하드코딩 금지: 다른 장비에서 실행 시 오류 발생.
* 배포 영상 폴더 문자열 직접 입력 금지: `KP.videos("항목명")` 사용. (배포 폴더명의 `(10개)`, `(30개)` 등은 원본 리터럴이므로 임의 수정 불가)
* 표본 간격(`0.5`), 해상도(`640`) 리터럴 사용 금지: 시각 어긋남 방지를 위해 `KP.SAMPLE_STRIDE_S`, `KP.DEFAULT_IMGSZ` 사용.
* 루트 변수명 혼용 금지: `KP.V` 하나로 통일.

---

## 2. 디렉토리 구조 및 역할

| 위치 | 담는 것 | 비고 |
| --- | --- | --- |
| 루트 (`model.py`, `score_kisa.py` 등) | 주 실행 진입점 | 위치 이동 불가 (상대경로 러너 및 프로세스명 추적 목적) |
| `scripts/` | 파이프라인 스크립트 | 새 스크립트는 이곳에 생성 (루트 생성 금지) |
| `scripts/_archive/<날짜>/` | 일회성·탐색 스크립트 보관 | 삭제 대신 이곳으로 이동 |
| `scripts/data_prep/` | 데이터 준비 단계 스크립트 |  |
| `configs/` | 큐 yaml, 데이터 계약(`datasets.yaml`) |  |
| `dash_v2/` | 대시보드 서버 및 프론트엔드 | 로그/데이터 파일 보관 금지 |
| `docs/` | 프로젝트 문서 |  |
| `data/원본데이터/` | 원본 (읽기 전용) | 삭제 및 덮어쓰기 절대 금지 |
| `data/학습데이터/` | 생성된 라벨, 학습/검증셋 |  |
| `results/<실험>/` | 실험 산출물 (`score.txt`, `meta.json` 등) |  |
| `runs/<실험>/` | 학습 가중치 및 설정 내역 |  |
| `logs/`, `logs/dash/` | 실행 로그 | Git 제외. 소스 폴더에 로그 파일 생성 금지 |
| `dumps/` | 채점 및 박스 덤프 | 영상 오버레이용 jsonl 등 |
| `_exp/` | 잡(Job) 목록 및 캐시 | Git 제외. 재생성 가능한 임시물 |
| `_kisa_port/` | 인증 제출 도구 (`tools/kisa_items.py`) | 수정/리팩터링 금지 (하단 4절 참고) |

---

## 3. 기록 및 계보 관리

### 기록 탐색 위치

* 이 모델의 학습 데이터: `results/MODELS.json` (가장 중요)
* 실험 설정/점수/mAP: `results/<실험>/{meta,score,eval_map,bench}`
* 학습 하이퍼파라미터: `runs/<실험>/args.yaml`
* 실행 과정 로그: `logs/queue/<실행>.log`
* 규칙 설정 교차검증(LOOCV): `results/loocv_results.json` (`scripts/loocv_all.py` 가 씀. 실험 하나에 매이지 않아 `results/` 바로 아래 둡니다)
* 규칙 훑기 결과(한 실험의 덤프로 침입·배회 규칙을 훑은 표, LOOCV 포함): `results/<실험>/rules.txt` (`scripts/rule_eval.py` 가 씁니다. 실험에 매이므로 그 실험 폴더 안에 둡니다. 2026-09-18)

배치가 이 규칙과 맞는지는 `.venv/bin/python scripts/check_layout.py --all` 로 확인합니다.

### 모델 계보 관리 (`results/MODELS.json`)

인증에 사용하는 가중치(`_kisa_port/weights/kisa/*.pt`)의 모든 정보(학습 데이터 구성, 파라미터 등)는 `MODELS.json`에 일원화합니다.

* 새 가중치 추가 시 반드시 JSON 항목을 추가하고 무결성 검사를 실행합니다.
* `python3 scripts/check_models.py` (무결성 검사)
* `python3 scripts/check_models.py --fix` (빈 항목 생성)


* 데이터셋 삭제 시 반드시 사전에 `MODELS.json`에 구성을 옮겨 적어야 합니다.

### 로그 및 산출물 작성 규칙

* `results/` 폴더 바로 아래에 `<이름>.txt` 형식의 임의 메모 생성 금지 (대시보드 파서 오류 유발). 메모는 `logs/_archive/<날짜>/`로 이동.
* 대시보드 인식을 위해 모든 실행 로그는 `logs/queue/<실행명>.log` 경로로 저장.
* 실험 설정은 사람이 수기로 적지 않으며, 스크립트 시작 시 `[설정] ...` 형태로 자동 출력되게 구성.

### 가중치 파일 관리 (혼동 주의)

가중치 폴더에 가중치 파일을 임의 복사하지 않으며, 스크립트 실행 시 인자(`--person-weights <pt>`)로 전달합니다.

1. `runs/<실험>/<모델>/weights/best.pt` : 학습 산출물 (실험 채점용)
2. `model/` : 운영 고정 모델
3. `_kisa_port/weights/kisa/` : 시험장 실제 사용 가중치 (`kisa_items.py` 참조 경로)

---

## 4. 임시·백업 파일 규칙

* 편집 전 백업 파일(`*.bak`, `*.bak_*`)을 소스 폴더에 남기지 않습니다. 이력 관리는 모두 Git을 사용합니다.
* 1회성 패치 스크립트는 `/tmp`에서 실행하며 저장소에 남기지 않습니다.
* 서버 재시작 및 긴 작업 로그는 반드시 `logs/` 디렉토리로 보냅니다.

---

## 5. 접근 및 수정 절대 금지 구역

* `data/원본데이터/`: 읽기 전용.
* `kisa_배포_검증영상`: 채점 전용. 어떠한 경우에도 학습셋이나 하드네거티브 배경으로 사용 금지.
* `_kisa_port/` (인증 제출 도구):
* 본시험 제출용 환경이므로 구조 변경 및 리팩터링 절대 금지.
* 현재 `.gitignore`로 폴더 전체가 버전 관리에서 제외되어 있어, 설정이 꼬일 경우 복구가 불가능합니다.