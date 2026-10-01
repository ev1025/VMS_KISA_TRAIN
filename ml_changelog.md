# ML → 대시보드 변경 기록 (ml_changelog.md)

계약 버전: v2
미확인: v1 · v2

## 규칙

### (a) ML 세션이 항목을 반드시 더하는 때

| 바뀐 곳 | 무엇이 바뀌면 |
|---|---|
| `results/<실험>/meta.json` | 키 추가 · 삭제, `item` · `status` · `phase` 값 집합 |
| `results/<실험>/score.txt` · `score_pc.txt` | 줄 형식. 기준 = `scripts/review_cache.py official()` 의 정규식 `RE_SEC` · `RE_ITEM` · `RE_BAD` · `RE_FIRE` · `RE_CLIP` 이 읽는 줄 |
| `dumps/review/` | `<실험>/<ckpt>/<item>/` 폴더 규칙, `<클립>.json` · `summary.json` · `_progress.json` 키 |
| `configs/history.yaml` | 상태(`s`) 값, 항목 키, 머리 `#` 주석 |
| `configs/result_blocks.yaml` | 최상위 키, 블록 키, `phases` 코드 · 이름표 |
| `configs/datasets.yaml` | 키, `use` 값, `gt` 값 집합 |
| 라벨 json | 손라벨 · sam2 · 정답라벨 스키마, 학습셋 `meta.json` 키 |
| 경로 | 파일 이동, 새 결과 폴더, 실험 · 학습셋 이름 규칙 |
| import 계약 이름(이름 · 인자 · 반환 모양) | `review_cache`: `eligible` · `official` · `_current` · `_datasets` · `CKPTS` · `FALL_EXP` · `FALL_CK` · `ITEM_OF` · `cache_dir` · `res_of` · `items_of` · `is_done` |
| | `review_post`: `compute_missing` · `top` · `is_fresh` · `VARIANTS` |
| | `kisa_items`: `ITEMS` · `make_judge` |
| `dash_v2/dash_meta.json` | 다시 만들어야 할 때(검수 편 목록 · 구역 · 정답이 바뀜. `build_dash_meta.py`) |
| 서버 B 사본 | `results/` · `dumps/review/` 를 B 로 옮겼을 때(무엇을 · 언제) |

### (b) 항목 서식

```
## vN · YYYY-MM-DD · 제목
- 바뀐 것:
- 영향:
- 옮기기:
- 쓴 사람:
- 확인:
```

| 줄 | 적는 것 | 누가 |
|---|---|---|
| 바뀐 것 | 파일 · 키 · 값 · 스키마 | ML |
| 영향 | 받는 엔드포인트 · js · 스크립트 · 스킬 | ML |
| 옮기기 | 소급 · 서버 B 복사 · 순서 조건 | ML |
| 쓴 사람 | `ML 세션` 또는 `풀스택 세션` | 쓴 쪽 |
| 확인 | 비워 둠 → 풀스택이 반영 뒤 `확인: YYYY-MM-DD dash_v2 <커밋 7자리>` 로 채우고, 같은 커밋에서 `dash_v2/serve_kisa.py` 의 `CONTRACT_VER = N` 을 올림 | 풀스택 |

### (c) 순서 · 번호

- 최신 항목이 맨 위. 맨 위 번호 = 계약 버전(머리 `계약 버전: vN`)
- 머리 `미확인:` = `확인:` 이 빈 항목 번호
- `scripts/check_contract.py` 가 맨 위 번호 · 머리 · `CONTRACT_VER` 를 대조(상수가 아직 없으면 경고만)

## v2 · 2026-10-01 · 히스토리 칸반: 상태 `아이디어` · 선택 키 `item` · `phase`

- 바뀐 것:
  - `configs/history.yaml` 항목 `s` 값 추가: `아이디어`. 전체 = `완료` · `진행` · `할 일` · `아이디어`
  - 선택 키 `item` ∈ {방화, 사람, 쓰러짐, 공통}. 없으면 공통
  - 선택 키 `phase` ∈ `result_blocks.yaml phases` 코드. 없으면 그리드 밖
  - Quick Add 규약: `{id, s: "아이디어", t}` 셋만(전역 필터가 항목이면 `item` 도). 범위 = 모델 개선 아이디어만

  | 칸반 | `s` | `dec` |
  |---|---|---|
  | Backlog | `아이디어` | 없음 |
  | To-Do | `할 일` | 없음 |
  | In Progress | `진행` | 없음 |
  | Done | `완료` | `채택` · `기각` · `보류` |

- 영향:
  - `/api/history`: `HS_ST` 에 `아이디어`, `HS_KEYS` 에 `item` · `phase`, `_hs_clean` 값 검사 2줄(item 집합 · phase ∈ phases)
  - `js/history.js`: 칸반 열 · Quick Add · 배지 · 전역 필터
  - ML 쪽: `sync_history.py ORDER` 에 `"아이디어": 3`(맨 아래), daily-report `SKILL.md` 히스토리 절(상태 · 키 · Quick Add · 할 일로 올릴 때 cond · item · phase 채움)
- 옮기기:
  - 기존 34항목 `item` 소급 = ML 이 서버 B `/api/history` 로. **풀스택이 새 `_hs_clean` 을 B 서버에 올린 뒤에만**(그 전엔 `_hs_clean` 이 모르는 키를 버림)
  - 원본은 B `configs/history.yaml` 하나. A 사본 복사 · 커밋은 ML
- 쓴 사람: ML 세션
- 확인:

## v1 · 2026-10-01 · 실험 단계 `phase`

- 바뀐 것:
  - `results/<실험>/meta.json` 선택 키 `phase`. 쓰는 곳 = `scripts/exp_queue.py write_meta()`, 값 = 큐 yaml 실험 항목의 `phase`. 없음 = 그리드 밖
  - `configs/result_blocks.yaml` 최상위 `phases` 표(코드 → 화면 이름표). 선택 키 `judge.tried[].phase`

  | 코드 | 이름표 |
  |---|---|
  | `grid0` | 0단계(옛 방화 판 앙상블 기준값, 학습 없음) |
  | `grid1` | 1단계(해상도 × 배치 비교) |
  | `grid2` | 2단계(승자 설정에서 한 요인씩: 데이터 · 합성 · 학습 설정 · 모델 크기) |
  | `grid3` | 3단계(규칙 고르기: 안 본 편에서 G · B · T, 채점편은 측정만) |
  | `grid4` | 4단계(결선: 상위 판 재확인 · 판정기 기술 · 앙상블 · 속도) |

  - 소급 규칙: `configs/queue_grid1*.yaml` 에 든 끝난 판 → `"phase": "grid1"`. 나머지는 비움(그리드 밖)
- 영향:
  - `/api/result_blocks`: `phases` 는 YAML 그대로 실림(풀스택 코드 수정 없음). `results_newdata.run()` 응답에 `phase` 1줄 노출 필요
  - 결과 탭: 단계 필터 · 배지. 검수 탭: 그룹 이름표
- 옮기기: 바뀐 `meta.json` 은 서버 B `results/<실험>/` 로 복사(ML). 10-01 소급 14판: grid1a~d · fire_map50 큐의 끝난 판 전부(`f640_grid_b720_20260930` 은 학습 중이라 끝난 뒤 소급)
- 쓴 사람: ML 세션
- 확인:

## 풀스택 → ML 요청

- (날짜) 요청 → ML 답(날짜)
