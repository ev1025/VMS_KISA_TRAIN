#!/bin/bash
V=/NHNHOME/WORKSPACE/26mss002_E3/vms; PY=$V/.venv/bin/python
cd $V
echo "=== 침입 재생성(person_v3, 포함억제 nms) ==="
CUDA_VISIBLE_DEVICES=0 $PY scripts/person_redump.py model/pre_test_v1/person_v3.pt --item 침입 --out dumps/intrusion_tile_v2 --stride 0.5 --grid 3 --overlap 0.2 --imgsz 960 --conf 0.15
echo "=== 배회 재생성(person_v2) ==="
CUDA_VISIBLE_DEVICES=0 $PY scripts/person_redump.py model/pre_test_v1/person_v2.pt --item 배회 --out dumps/loiter_trk_id_v2 --stride 0.5 --grid 3 --overlap 0.2 --imgsz 960 --conf 0.15
echo "ALL DONE"
