# 범용 ELF 실행 실험 도구

`src/elf_lab.py`는 외형용 ELF와 실제 동작을 담당할 원본 실행 파일을 별도로 받습니다.
예를 들어 심볼 포함 curl을 외형으로, jq를 실행 대상으로 지정하면 결과 파일에는
curl 코드·문자열·심볼·디버그 정보가 남고, 실행하면 jq가 원래 인자를 받아 처리합니다.
원본 파일이나 시스템 명령 경로는 수정하지 않습니다.

## 원본 프로그램 실행 모드

```sh
python3 src/elf_lab.py build output/curl-symbols/curl \
  --payload ./jq -o output/my-experiment/curl
printf '{"items":[1,2,3]}\n' | ./output/my-experiment/curl '.items | add'
# 6
python3 src/elf_lab.py verify output/curl-symbols/curl output/my-experiment/curl
```

첫 번째 입력은 **외형용 바이너리**, `--payload`는 **실제 실행할 원본 파일**입니다.
외형용 입력은 curl에 한정되지 않습니다. 파일 이름이나 고정 함수 주소에 의존하지 않습니다.

생성한 결과의 새 진입점은 `execve`로 원본 파일을 직접 실행합니다.
`argv[0]`은 실행 대상의 절대 경로로 설정하고 나머지 인자는 그대로 전달합니다.
환경변수, 현재 디렉터리, 표준 입출력, 상속 가능한 파일 디스크립터는 유지됩니다.
별도 자식 프로세스를 만들지 않으므로 종료 코드와 신호 동작도 실행 대상이 결정합니다.
원본 경로를 사용하므로 `$ORIGIN` 기반 공유 라이브러리와 실행 파일 주변의 리소스도
원래 위치에서 찾습니다. 실행 대상이 심볼릭 링크이면 링크 이름을 보존합니다.

이 모드는 실행 대상 원본 파일을 빌드 시 기록한 절대 경로에 유지해야 합니다.
실행 대상을 내장한 단일 파일 패키지는 아닙니다. 실행 후 `/proc/self/exe` 등에서
보이는 프로세스 정체성은 실제 실행 대상입니다. 상대 경로로 직접 실행했을 때의
`argv[0]` 문자열까지 같다는 뜻은 아니며, 실행 대상을 같은 절대 경로로 직접 실행한
경우를 기준으로 동작을 비교합니다. PID, 실행 시각 등 매 실행마다 달라지는 값은 제외합니다.

curl의 인터프리터 프로그램 헤더를 새 헤더 테이블에서 제외하여 curl의 동적 로더나
라이브러리 초기화가 실행되지 않게 합니다. curl 내부 함수의 기계어와 기존 심볼 테이블은
그대로 남습니다. 런처는 libc가 필요 없고, 실행 대상만 자신의 원래 로더를 사용합니다.

매니페스트에는 외형 원본·결과 및 실행 대상의 해시와 경로가 기록됩니다.
`verify`는 실행 대상이 존재하고 빌드 시 해시와 같은지도 검사합니다.
실행 시에는 해당 경로의 현재 파일을 실행하므로, 이후 교체된 파일을 고정하거나
인증하는 기능은 아닙니다. 대상이 없어졌으면 종료 코드 127, 다른 execve 오류는 126입니다.

기존 에코 서버 프로그램도 실행 대상으로 지정할 수 있습니다.

```sh
python3 src/elf_lab.py build output/curl-symbols/curl \
  --payload output/curl-socket/curl -o output/my-server/curl
CURL_SOCKET_PORT=19090 ./output/my-server/curl
```

이때 포트·프로토콜·연결 수·종료 방식은 실행 대상 원본이 결정합니다.
도구의 `--port`는 아래 내장 에코 모드에만 사용하며 `--payload`와 함께 사용할 수 없습니다.

## 요구 환경과 지원 범위

- Python 3.10 이상, GNU gcc / ld / objcopy, Linux x86-64.
- little-endian ELF64의 ET_EXEC / ET_DYN 실행 파일.
- 정적 링크, 동적 링크, PIE, static PIE, stripped / unstripped 파일.
- 섹션 테이블이 없는 실행 파일도 지원하며 결과에도 섹션 테이블을 만들지 않습니다.
- 실행 대상의 동적 인터프리터와 공유 라이브러리는 실행 환경에 계속 필요합니다.
- `--payload` 모드는 외형용 ELF의 공유 라이브러리에 의존하지 않습니다.
- PE, Mach-O, ARM, ELF32, 공유 라이브러리 전용 파일, 확장 ELF 헤더 개수 표현은 지원하지 않습니다.

형식이 맞더라도 자체 무결성 검사, 특수 로더, 로더 초기화 부작용을 가진 모든 바이너리의
동작을 보장하지 않습니다. `inspect`는 구조 검사이며 실제 실행 호환성 테스트가 아닙니다.

## 내장 에코 모드

`--payload`를 생략하면 기존 실험용 단일 연결 에코 서버를 결과 파일에 내장합니다.
이 모드에만 아래 포트 설정과 에코 전용 동작 설명이 적용됩니다.

저장소 루트에서 실행합니다. `inspect`와 `verify`는 입력 파일을 실행하지 않습니다.

```sh
# 구조, 진입점, 인터프리터, 심볼 테이블 유무, SHA-256 확인
python3 src/elf_lab.py inspect /usr/bin/ls

# 새 경로에 결과 생성; 기존 파일이 있으면 덮어쓰지 않고 실패
python3 src/elf_lab.py build /usr/bin/ls -o output/my-experiment/ls --port 19090

# 원본과 결과, 자동 생성된 .manifest.json을 이용한 구조·해시 검증
python3 src/elf_lab.py verify /usr/bin/ls output/my-experiment/ls
```

입력/출력 경로에 공백이 있으면 셸에서 따옴표로 감싸면 됩니다.
실행 파일 옆에 `ls.manifest.json`이 생성됩니다. 원본·결과 해시, 진입점,
페이로드 해시, 동작 설정, 구조 검증 결과를 포함합니다.
매니페스트는 재현·변경 추적용이며 디지털 서명이 아닙니다.

여러 입력에도 같은 명령을 반복 적용할 수 있습니다.

```sh
for name in ls cat true; do
  python3 src/elf_lab.py build "/usr/bin/$name" -o "output/batch/$name" || break
done
```

생성한 바이너리는 원래 명령 인자를 무시합니다. 예를 들어 `ls --version`도
에코 서버를 실행합니다. 원래 `main`의 기계어와 심볼은 남지만 호출되지 않습니다.

## 실행 및 에코 확인

첫 번째 터미널에서:

```sh
# 기본 포트는 빌드 시 --port로 지정한 값; 생략 시 18080
./output/my-experiment/ls

# 실행 시 환경변수로 포트 덮어쓰기
ELF_ECHO_PORT=19091 ./output/my-experiment/ls
```

바인딩 주소는 항상 `127.0.0.1`입니다. 한 연결을 받고, 클라이언트가 송신을
종료하면 남은 데이터를 반환한 뒤 종료 코드 0으로 끝납니다.
연결이 오기 전에는 대기합니다. 잘못된 포트, 포트 충돌, 소켓·입출력 오류는
종료 코드 1을 반환합니다. 포트 범위는 1–65535이며 빈 환경변수도 오류입니다.

다른 터미널에서 환경변수 예제를 확인하려면:

```sh
python3 - <<'PY'
import socket
with socket.create_connection(('127.0.0.1', 19091), timeout=3) as client:
    client.sendall('hello / 테스트\n'.encode())
    client.shutdown(socket.SHUT_WR)
    chunks = []
    while part := client.recv(4096):
        chunks.append(part)
    print(b''.join(chunks).decode(), end='')
PY
```

## 기존 curl 작업과의 관계

기존 구현은 `main → tool_init_stderr → tool_stderr_read_hook`에서 서버를 실행했습니다.
이 방식은 curl 소스와 해당 함수에 의존합니다. 소스 없는 임의 바이너리에서는
동일한 의미의 함수·호출 지점·스택 배치를 자동으로 식별할 수 없습니다.

새 도구는 추가 RX LOAD 세그먼트에 위치 독립적인 실행 어댑터를 배치하고 ELF 진입점을
그 코드로 변경합니다. 프로그램 헤더 테이블도 새 LOAD에 매핑하고 PT_PHDR을 갱신합니다.
원래 LOAD 주소, 함수 명령어, 심볼 및 문자열은 보존합니다. 섹션이 있는 입력에는
`.text.exec_lab` 또는 `.text.echo_lab`을 추가합니다. 원본 파일 내용은 첫 64바이트 ELF 헤더를 제외하고
바이트 단위로 보존합니다. 코드에는 고정된 호스트 주소나 libc 호출이 없습니다.

```text
--payload: 커널 → 새 진입점 → execve(실행 대상) → 실행 대상의 원래 동작
내장 에코: 커널 → 필요하면 외형의 동적 로더 → 새 진입점 → 에코 서버 → 종료
외형용 바이너리의 원래 진입점 / main은 두 모드 모두 실행하지 않음
```

내장 에코 모드에서는 외형의 라이브러리 초기화가 새 진입점보다 먼저 실행될 수 있습니다.
원래 `main`을 실제로 거치도록 만드는 내부 훅 선택은 이 도구의 지원 범위가 아닙니다.
기존 build-id도 보존되므로 결과 식별에는 매니페스트의 SHA-256을 사용합니다.
디버그 경로 치환, 문자열 삭제, 심볼 이름 변경은 이 변환에 포함되지 않습니다.

## 검증

```sh
# 구조, 재현성, 오류 입력, 덮어쓰기 방지, 변조 감지, 실행 시 포트 검증
python3 -m unittest discover -s tests -v

# 로컬 소켓 사용이 가능한 환경: 실제 에코와 포트 충돌까지 포함
ELF_LAB_NETWORK_TESTS=1 python3 -m unittest discover -s tests -v
```

테스트는 저장소의 jq와 심볼 포함 curl, 시스템 ls, 컴파일한 동적 ET_EXEC 및
static PIE, 섹션 테이블을 제거한 true를 입력으로 사용합니다.
테스트용 생성물은 임시 디렉터리에서 정리되며 서버 프로세스도 종료됩니다.
일반 테스트에서는 네트워크 관련 테스트 2개가 명시적으로 skip됩니다.

6종 입력 모두에서 텍스트, UTF-8, 빈 메시지, 128 KiB 이진 데이터의 에코와
EOF 이후 종료, 포트 충돌 실패, 잘못된 포트 6개를 검증했습니다.
샘플 결과는 `output/elf-lab/curl`, `output/elf-lab/jq`, `output/elf-lab/ls`입니다.

원본 실행 모드는 6종 외형에서 인자·환경변수·작업 디렉터리·stdin/stdout/stderr·
종료 코드·신호 종료 및 `/proc/self/exe` 결과를 원본 직접 실행과 비교합니다.
상속 파일 디스크립터, 특수문자 포함 경로, 심볼릭 링크 이름, 대상 누락·변조도 검사합니다.
curl의 `nm -a` 출력이 원본과 동일하고 `main` 심볼이 남는지 확인합니다.
샘플 `output/elf-exec/curl-jq`와 `output/elf-exec/curl-printf`는 각각 jq와 printf를 실행합니다.
