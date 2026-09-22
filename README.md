# VMS_KISA

KISA 지능형 CCTV 성능 인증 프로젝트 (방화·화재 / 침입 / 배회 / 쓰러짐).

- 레포 규약·폴더 구조: [`CLAUDE.md`](CLAUDE.md)
- 데이터 활용 대장(활용여부·이유·부적합): [`docs/data.md`](docs/data.md)


## 실험 결과

지금까지 돌린 실험 95건의 점수는 [results/SUMMARY.md](results/SUMMARY.md) 에 있다.
`results/` 자체는 용량 때문에 깃에 없으므로, 클론만 한 장비에서는 이 파일을 본다.
실험이 끝날 때마다 `python scripts/build_summary.py` 로 다시 만든다.
