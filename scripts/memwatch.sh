#!/bin/bash
# 3초마다 메모리·GPU 를 남긴다. OOM(rc=-9) 이 나면 직전 줄이 원인을 말해 준다.
# /tmp 은 noexec 라 실행이 안 된다. 저장소 안에 두고 'bash scripts/memwatch.sh' 로 돌린다.
while true; do
  read -r _ tot used free shared bc avail < <(free -g | sed -n 2p)
  top=$(ps -eo rss,comm --sort=-rss --no-headers | head -3 | awk '{printf "%s(%.0fG) ", $2, $1/1048576}')
  gpu=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
  echo "$(TZ=Asia/Seoul date +%H:%M:%S) used=${used}G avail=${avail}G shared=${shared}G cache=${bc}G gpu=${gpu}M | $top"
  sleep 3
done
