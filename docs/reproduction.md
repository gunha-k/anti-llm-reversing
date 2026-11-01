# 새 컴퓨터에서 준비하고 실행하기

저장소에는 자체 소스, 문서, 테스트, 환경 구성 파일만 포함한다.
`build/`, `output/`, 원본 `jq`, `.o`, 실행 파일과 외부 프로젝트의 전체 소스는 포함하지 않는다.
필요한 외부 입력은 `scripts/downloads.json`의 HTTPS URL에서 다운로드하고,
고정 SHA-256과 일치할 때만 사용한다. jq는 주소에 의존하는 기존 실험을 위해
소스 재빌드 대신 공식 jq 1.8.2 Linux amd64 바이너리를 받는다.

## Docker 사용

Docker가 실행 중이고 인터넷에 접근할 수 있어야 한다.

```sh
git clone https://github.com/gunha-k/anti-llm-reversing.git
cd anti-llm-reversing
docker build --platform linux/amd64 -t anti-llm-reversing .

# 노트·셸·압축 프로그램만 빌드하고 테스트
docker run --rm --platform linux/amd64 anti-llm-reversing

# 외부 입력 다운로드부터 전체 실험 빌드·검증까지
docker run --name reversing-lab --platform linux/amd64 \
  anti-llm-reversing python3 scripts/reproduce.py all --jobs 2

# 생성물을 로컬로 가져오기 (컨테이너는 종료되어도 복사 가능)
docker cp reversing-lab:/workspace/output ./output
docker cp reversing-lab:/workspace/examples/standalone ./standalone-results
```

컨테이너 이름이 이미 있으면 다른 이름을 지정한다. 종료된 컨테이너는
`docker start`로 작업 상태를 복구하는 기능을 제공하지 않는다. 재검증은 새 컨테이너에서 한다.
ARM 머신의 `linux/amd64` 실행은 에뮬레이션 지원이 필요하며 네이티브보다 느릴 수 있다.
컴파일된 ELF는 Linux용이므로 Windows/macOS에서는 컨테이너 또는 Linux VM 안에서 실행한다.
호스트에서 복사한 ELF를 실행하려면 호환되는 x86-64 Linux 공유 라이브러리가 필요하다.

## Ubuntu 24.04 x86-64에 직접 설치

```sh
sudo apt-get update
sudo apt-get install -y python3 build-essential binutils git curl ca-certificates \
  xz-utils pkg-config libssl-dev zlib1g-dev libncurses-dev
git clone https://github.com/gunha-k/anti-llm-reversing.git
cd anti-llm-reversing
python3 scripts/reproduce.py all --jobs 2
```

준비 스크립트는 sudo나 시스템 패키지 설치를 실행하지 않는다.
Python 3.12 이상이 필요하며 저장소 경로에는 공백·셸 특수문자를 넣지 않는다.
최초 실행에는 인터넷과 다운로드·빌드 공간이 필요하다. `all`은 컴퓨터에 따라 수 분 이상 걸린다.
로컬 TCP 검증은 127.0.0.1의 임시 포트를 사용하며 외부 서비스에 접속하지 않는다.

## 대상 선택

| 명령 인자 | 준비 및 검증 범위 |
|---|---|
| `standalone` | note, minish, rle의 `.o`·실행 파일 및 동작 테스트 |
| `fetch` | 외부 입력 5개 다운로드 및 해시 확인만 수행 |
| `curl` | 원본 디버그 curl, hello·echo 예제 및 curl 통합 테스트 |
| `native` | SQLite·Vim·Git echo 예제, 구조·실제 TCP 동작 비교 |
| `legacy` | jq 심볼 변형·문자열 변형·기존 소켓 실험 및 검증 |
| `all` | 위 빌드·검증과 범용 ELF 테스트(네트워크 테스트 포함) |

`fetch` 뒤에 다른 대상을 실행하면 확인된 다운로드를 재사용한다.
`curl`, `native`, `all`은 빈 출력 디렉터리가 있는 새 복제본에서 실행한다.
기존 입력의 해시가 다르거나 출력 경로가 이미 있으면 덮어쓰지 않고 중단한다.
Vim 개발 파일은 시스템 `/usr`를 사용한다. 기존 방식으로 `.deb`를 추출했다면
`--deps /absolute/path/to/deps`로 그 루트를 지정할 수 있다.

## 자체 프로그램 사용

```sh
./examples/standalone/note write memo.txt 'hello'
./examples/standalone/note read memo.txt
./examples/standalone/minish -c 'printf hello'
./examples/standalone/rle compress memo.txt memo.rle
./examples/standalone/rle decompress memo.rle restored.txt
```

## 재현 범위

외부 입력 버전과 해시는 고정하지만 시스템 패키지·컴파일러 버전까지 고정하지 않는다.
생성 ELF의 SHA-256이나 심볼 주소가 과거 실험과 같다는 보장은 없다.
검증은 구조와 지정한 예제의 동작을 확인하며 upstream 전체 테스트를 대신하지 않는다.

과거 README와 문서의 파일 크기·심볼 개수·검증 결과는 당시 환경의 기록이다.
새 검증 보고서는 현재 환경의 `output/`에 생성된다.
`output/curl-socket/curl`은 새 절차에서 `curl_main_hook.py`와 echo.c로 생성하며
`HOOK_ECHO_PORT`를 사용한다. 과거 `tool_stderr_read_hook` 방식 전용인
`verify_curl_socket.py`, `sanitize_curl_debug_paths.py`는 이 재현 절차에서 실행하지 않는다.
그 과거 변형의 정확한 재생성은 `all`의 범위에 포함하지 않는다.
