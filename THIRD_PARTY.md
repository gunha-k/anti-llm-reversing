# 외부 입력

이 저장소는 아래 외부 프로젝트의 전체 소스나 실행 파일을 포함하지 않습니다.
다운로드 URL과 고정 SHA-256은 `scripts/downloads.json`에 기록합니다.
준비 스크립트 실행 시 외부 입력을 로컬에 받아 빌드하며, 다운로드와 빌드 결과는
`.gitignore` 및 `.dockerignore`로 제외합니다.

| 입력 | 버전 | 출처 및 라이선스 안내 |
|---|---|---|
| curl | 8.22.0 | https://curl.se/docs/copyright.html |
| SQLite | 3.50.4 | https://www.sqlite.org/copyright.html |
| Vim | 9.1.0000 | https://github.com/vim/vim/blob/v9.1.0000/LICENSE |
| Git | 2.50.1 | https://github.com/git/git/blob/v2.50.1/COPYING |
| jq (공식 Linux amd64 실행 파일) | 1.8.2 | https://github.com/jqlang/jq/releases/tag/jq-1.8.2 |

다운로드한 외부 소스의 저작권·라이선스 파일을 유지해야 합니다.
생성한 수정본 바이너리를 별도로 배포할 때는 각 프로젝트 및 링크된 라이브러리의
라이선스 조건을 확인해야 합니다. 이 문서는 외부 코드의 라이선스를 대체하지 않습니다.
자체 코드에 적용할 프로젝트 라이선스는 아직 지정하지 않았습니다.
