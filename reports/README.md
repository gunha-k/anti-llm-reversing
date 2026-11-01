# 검증 기록

`clean-container/`는 외부 입력을 새로 다운로드한 Ubuntu 컨테이너에서 수행한 재현 검증입니다.

`historical/`은 기존 로컬 실험의 JSON 보고서 사본입니다.
워크스페이스 절대 경로만 `<workspace>`로 바꾸었으며 ELF 해시와 측정값은 원래 기록입니다.
이는 현재 컴퓨터에서 다시 검증했다는 의미가 아닙니다.
새 컴퓨터의 보고서는 `python3 scripts/reproduce.py all` 실행 시 `output/`에 생성됩니다.
