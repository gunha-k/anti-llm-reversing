# 빈 Ubuntu 컨테이너 재현 검증

2026-11-01, Linux x86-64, Ubuntu 24.04 Docker 환경에서 확인했다.
호스트의 build/, output/, jq, .o와 예제 실행 파일을 Docker context에서 제외했다.
외부 입력 5개를 HTTPS로 새로 받고 저장소에 고정한 SHA-256을 검증했다.

- `python3 scripts/reproduce.py all --jobs 4`: 종료 코드 0.
- standalone: 3개 테스트 통과.
- curl: 9개 테스트 통과. 첫 전체 실행에서 TCP 테스트는 생략되었으며,
  동일 컨테이너에서 `ELF_LAB_NETWORK_TESTS=1`로 9개 모두 다시 실행하여 통과했다.
  최종 준비 스크립트는 이 환경변수를 기본으로 설정한다.
- 범용 ELF: 로컬 TCP 검사를 포함한 14개 테스트 통과.
- SQLite/Vim/Git: 각각 원본 빌드, 예제 링크, 구조 검사, 포트 오류와
  실제 TCP 에코·SIGTERM·포트 충돌 검증 통과 (`native-main-hook.json`).
- jq: 3개 변형에서 각각 21개 동작 비교 통과 (`jq-variants.json`).
- 문자열 치환 및 jq 소켓 변형 빌드·검증 통과 (`socket-mode.json`).

외부 프로젝트 전체 upstream 테스트나 모든 사용자 입력 프로그램에 대한
호환성 검증은 아니다. `/workspace` 경로는 검사에 사용한 컨테이너 내부 경로이다.
