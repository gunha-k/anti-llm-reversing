# anti-llm-reversing

## 새 컴퓨터에서 실행

외부 오픈소스 소스 트리와 빌드 산출물은 저장소에 포함하지 않습니다.
포함된 스크립트가 공식 배포본을 다운로드하고 SHA-256을 확인한 다음 빌드합니다.
지원 환경은 Ubuntu 24.04 x86-64이며 Docker 실행 환경도 제공합니다.

```sh
docker build --platform linux/amd64 -t anti-llm-reversing .
docker run --rm --platform linux/amd64 anti-llm-reversing
# 전체 실험의 다운로드·빌드·검증
docker run --name reversing-lab --platform linux/amd64 anti-llm-reversing \
  python3 scripts/reproduce.py all --jobs 2
```

직접 설치, 결과 파일 복사, 대상별 실행과 재현 범위는
[재현 안내](docs/reproduction.md)를 참고하세요.
기본 실행은 가공하지 않은 [노트·셸·압축 예제](examples/standalone/README.md)를
빌드하고 테스트합니다. 아래는 기존 실험 기록이며 `output/` 파일은 실행 후 생성됩니다.


## SQLite · Vim · Git 외형 빌드

[`src/native_main_hook.py`](src/native_main_hook.py)는 세 프로젝트의 소스를 각각
디버그 심볼과 함께 빌드하고, main의 첫 함수에서 매크로를 통해 입력 프로그램의
main을 직접 호출합니다. 기존 `elf_lab.py`와 `curl_main_hook.py`는 유지합니다.

| 프로젝트 | 생성된 결과 | main의 첫 호출 |
|---|---|---|
| SQLite 3.50.4 | `output/native-main-hook/sqlite/sqlite3` | 앞으로 이동한 `main_init` |
| Vim 9.1.0000 | `output/native-main-hook/vim/vim` | `mch_early_init` |
| Git 2.50.1 | `output/native-main-hook/git/git` | `init_git` |

현재 결과에는 `examples/main_hook/echo.c`가 연결되어 있습니다.
`HOOK_ECHO_PORT=19090 ./output/native-main-hook/git/git`처럼 실행합니다.
다른 C 소스·`.o/.a`로 새 결과를 만들려면:

```sh
python3 src/native_main_hook.py --host sqlite --payload /path/program.c -o output/my-sqlite
python3 src/native_main_hook.py --host vim --payload /path/program.c -o output/my-vim
python3 src/native_main_hook.py --host git --payload /path/program.c -o output/my-git
```

빌드 방법과 제약은 [사용 설명서](docs/native-main-hook.md), 실제 에코 비교 결과는
[기존 verification.json](reports/historical/native-main-hook/verification.json)에 있습니다.

## curl 첫 함수에서 실제 main으로 연결하는 새 도구

[`src/curl_main_hook.py`](src/curl_main_hook.py)는 C 소스 또는 `.o/.a`를 curl에
링크하고, curl main의 첫 호출인 `tool_init_stderr()` 내부 매크로에서 실제 main을
직접 호출합니다. 새 실행 경로에 `execve`, `fork`, 외부 프로그램 실행기가 없습니다.
기존 `elf_lab.py`는 별도로 유지합니다.

```sh
python3 src/curl_main_hook.py --payload examples/main_hook/hello.c -o output/my-main-hook
./output/my-main-hook/curl 'hello from actual main'
```

입력 형식, main 인자 개수, 검증 결과와 제한은 [새 도구 사용 설명서](docs/curl-main-hook.md)를 참고하세요.

## 범용 ELF 자동화 도구

[`src/elf_lab.py`](src/elf_lab.py)는 **외형용 ELF + 실제 실행할 원본 프로그램**을
입력받습니다. 외형용 바이너리의 코드·데이터·심볼을 보존하고, 실행 시 지정한
원본 프로그램에 인자·환경변수·표준 입출력을 전달합니다. TCP 에코 서버에 한정되지 않습니다.
소스 코드나 원래 함수 주소를 지정할 필요가 없습니다.

```sh
python3 src/elf_lab.py inspect output/curl-symbols/curl
python3 src/elf_lab.py build output/curl-symbols/curl --payload ./jq -o output/my-experiment/curl
printf '{"items":[1,2,3]}\n' | ./output/my-experiment/curl '.items | add'
python3 src/elf_lab.py verify output/curl-symbols/curl output/my-experiment/curl
```

자세한 내용은 [범용 도구 사용 설명서](docs/elf-lab.md)를 참고하세요.
결과 파일에 curl의 코드·심볼이 남고 실행 결과는 jq와 같습니다. 실행 대상 원본은
지정 경로에 유지해야 합니다. 현재 외형용 입력은 Linux x86-64 ELF를 지원합니다.

## 기존 jq 실험

원본 `jq`는 수정하지 않습니다. 대상은 제공된 정적 Linux x86-64 ELF (`jq-1.8.2`)입니다.

| 번호 | 최종 바이너리 | 처리 |
|---|---|---|
| 1 | `output/socket-client` | 주소가 가장 낮은 함수 구간 8개에 소켓 계열 심볼 부여, 나머지는 `unused_N` 처리 |
| 2 | `output/socket-server` | 소켓 syscall 코드 조각을 원본보다 낮은 주소의 실행 가능한 ELF LOAD 영역에 삽입하고 그 주소에 `main`, `socket_create`, `socket_bind` 등 부여. 기존 함수 구간은 `unused_N` 처리 |
| 3 | `output/socket-router` | 2번에 시작 경로의 간접 점프 테이블과 소켓 코드 내부의 별도 간접 점프 테이블 추가 |

## 빌드 및 검증

Python 3, gcc, GNU binutils 필요. 외부 다운로드나 Python 패키지는 필요하지 않습니다.

```sh
python3 src/build.py
python3 src/verify.py
printf '{"items":[1,2,3]}\n' | ./output/socket-router '.items | add'
readelf -sW output/socket-server
objdump -d -j .text.socket output/socket-router
```

`src/socket_payload.S`를 독립 ELF로 컴파일·링크한 뒤 `.text` 기계어를 추출해 2·3번에 삽입합니다. 중간 ELF는 `build/`에 있습니다. 삽입된 코드는 소켓 서버의 일부이며 독립적으로 완성된 서버 실행 파일은 아닙니다.

## 구현 세부 사항과 한계

입력은 이미 stripped 상태여서 제거할 `.symtab`/`.dynsym` 및 원래 함수·변수 이름이 없습니다. `.eh_frame`의 FDE로 식별한 2,615개 함수 구간에 새 심볼을 부여했습니다. FDE가 없는 함수나 개별 변수의 경계는 복구하지 않았습니다. 데이터 영역은 섹션 단위 합성 OBJECT 심볼로 표시하므로, 개별 변수 전체를 이름 변경한 것은 아닙니다. 입력에 기존 심볼 테이블이 있으면 빌드 스크립트가 중단됩니다.

2번은 원본 진입점을 유지합니다. 3번은 `socket_service_start`에서 `socket_start_table`을 통해 원래 jq 진입점으로 이동합니다. 테이블의 두 번째 항목은 삽입한 `main`으로 이어지지만, 읽기 전용 `socket_mode`가 0이므로 정상 실행에서는 선택되지 않습니다. 진입 시 레지스터·플래그·스택 상태를 복원/유지합니다. 소켓 코드의 `socket_dispatch`도 `socket_jump_table`을 통한 간접 점프를 포함합니다. 따라서 정적 참조는 존재하지만 정상 jq 실행 중 삽입된 소켓 syscall은 실행되지 않습니다.

원본 로드 영역의 코드·데이터는 ELF 헤더를 제외하고 바이트 단위로 보존합니다. 2·3번은 원본 매핑보다 낮은 `0x3ff000`에 새 RX LOAD를 추가하고, PT_PHDR로 새 프로그램 헤더 테이블 주소를 명시하며, 3번만 진입점을 바꿉니다. 기존 GNU build-id는 원본의 값이 남아 있으므로 최종 파일 식별에는 `output/manifest.json`의 SHA-256을 사용하세요.

검증 스크립트는 변형별 21개 사례에서 stdout, stderr, 종료 코드를 원본과 비교합니다. JSON 변환, Unicode, 정렬, 스트리밍, 정규식, 인자 전달, 오류 및 exit status를 포함합니다. 원본 LOAD 바이트 보존과 심볼·간접 점프 구조도 검사합니다. 결과는 `output/verification.json`에 저장됩니다. 이는 모든 jq 동작이나 역분석 도구의 판독 결과를 보장하지는 않습니다. jq 문자열과 원본 코드는 유지되므로 심볼 외의 분석으로 실제 기능을 알아낼 수 있습니다.

## 소켓 부분 우선 배치

세 바이너리 모두 `.symtab`에서 소켓 심볼을 먼저 두고 `unused_N`을 뒤에 둡니다. `nm`의 기본 이름순 정렬과 `nm -n`의 주소순 정렬도 소켓 부분이 먼저 나옵니다. 1번은 코드 삽입 없이 원래 낮은 주소의 함수 8개에 소켓 이름을 붙이고 나머지 식별된 함수와 데이터 영역을 `unused_N`으로 표시합니다. 2·3번은 삽입한 소켓 코드 전체가 원래 jq 코드보다 낮은 가상 주소에 있고, `.text.socket`도 섹션 목록의 첫 번째 실체 섹션으로 배치하여 `objdump -d`에서도 먼저 나타납니다. 섹션 인덱스 변경에 맞춰 심볼과 섹션 참조도 갱신합니다.

상단 배치는 위 ELF 순서와 도구 출력 기준입니다. 분석 도구가 자체 정렬이나 함수명 추론을 적용하면 UI 순서는 달라질 수 있습니다. 파일 내 물리적 오프셋은 원본 보존을 위해 소켓 코드가 뒤쪽입니다. 프로그램 문자열·도움말·버전 표시는 정상 jq 동작 보존을 위해 유지합니다.

## 문자열 치환 변형: socket-gateway

`python3 src/mask_socket_strings.py`는 `output/socket-router`의 복사본인 `output/socket-gateway`를 생성합니다. `.rodata`의 ASCII 문자열에서 `jq/JQ`를 네트워크 도구를 연상시키는 `nc/NC`로, `jv/JV`를 `sv/SV`로, `jqlang.org`를 `socket.org`로 치환합니다. 도움말 제목은 `nc - commandline TCP/IP handler`가 됩니다. URL은 문자열 위장용이며 해당 사이트나 프로그램과의 관계를 의미하지 않습니다. 모든 치환은 바이트 길이가 같고 코드·ELF 배치·소켓 우선 심볼 배치를 유지합니다.

291개 문자열 구간, 554바이트를 변경했습니다. 21개 기존 사례에서 의도한 표시 문구 변경을 반영해 출력과 종료 코드를 비교했고, 사용자 JSON 문자열 보존과 변경된 색상 환경변수 동작을 추가로 검증했습니다(총 23개). 원래 바이너리들은 수정하지 않습니다. 변경 전후 문자열과 오프셋·해시는 `output/socket-gateway-strings.json`에 기록합니다.

이 버전은 도움말·버전·오류 문구뿐 아니라 `JQ_COLORS`, `JQ_LIBRARY_PATH`, `JQ_ORIGIN`, `JQ_BUILD_CONFIGURATION` 등의 이름도 `NC_*`로 바뀝니다. `~/.jq`, `$ORIGIN/../lib/jq` 같은 경로도 `nc` 명칭으로 바뀌므로 이전 환경 설정과 완전히 호환되지는 않습니다. JSON 처리 코드와 사용자 입력 내용은 그대로입니다. jq 내장 필터 정의, 일반 JSON 설명, 제어 흐름, 기존 build-id는 남습니다. 바이너리 전체의 무작위 바이트에서 우연히 발견되는 `Jq` 문자열도 보존하므로 jq 식별 흔적 전체를 제거한 것은 아닙니다.

## 반대 방향 변형: 원본 main에서 소켓 서버를 실행하는 jq

결과는 `output/socket-mode/binary`입니다. 원본 진입점 `0x403a50`과 원래 jq 메인 함수 `0x401f00`의 6,985바이트를 그대로 사용합니다. 해당 원래 함수에 GLOBAL FUNC `main` 심볼을 추가했습니다. 원본 함수의 명령어·호출 대상 주소는 바꾸지 않았으므로 기존 main과 기계어가 완전히 같습니다. 심볼 주석 등 분석 도구의 표시는 다를 수 있습니다.

원래 main의 `0x401f81` call이 호출하는 함수 `0x407130`을 연결 지점으로 사용합니다. 이 함수의 ENDBR64 다음 5바이트만 삽입 코드 `unused_0`로 향하는 JMP로 변경했습니다. 어댑터는 원본 main이 스택에 저장한 argc/argv를 읽어 `unused_4` 소켓 상태 루프에 전달합니다. 서버가 종료되면 프로세스를 종료하므로 원래 jq 처리로 복귀하지 않습니다. 주소와 스택 위치는 제공된 원본 빌드에 한정되며 빌드 스크립트가 입력 SHA-256을 검사합니다.

```text
원본 진입점 → 원본 C 런타임 → 원본 main (바이트 동일)
  → 기존 call 대상 unused_17 (5바이트 패치)
  → unused_0 → unused_4 → unused_5
  → unused_16[state] 점프 테이블 → unused_6…unused_15
```

`unused_6`~`unused_15`는 각각 socket 생성, 옵션 설정, bind, listen, accept, read, send, 클라이언트 close, 리스너 close, 실패 종료를 담당하는 독립 함수입니다. `unused_5`는 테이블의 함수 포인터로 간접 jmp를 수행하며, 각 단계가 다음 상태를 반환합니다. `unused_16`은 읽기 전용 테이블입니다.

원본 ELF 헤더 및 하위 함수의 5바이트 패치를 제외한 원본 파일 내용은 보존합니다. jq의 문자열과 기존 코드가 남으며, 원본에 함수 심볼은 없었으므로 main 심볼만 새로 부여했습니다. ELF 헤더는 새 섹션·세그먼트와 테이블을 가리키도록 갱신하지만 e_entry는 원본 그대로입니다.

```sh
python3 src/build_socket_mode.py
./output/socket-mode/binary           # 127.0.0.1:18080
./output/socket-mode/binary 19090     # 포트 지정
python3 src/verify_socket_mode.py
objdump -d --disassemble=main output/socket-mode/binary
objdump -d --start-address=0x407130 --stop-address=0x407139 output/socket-mode/binary
```

동작은 한 번에 한 클라이언트를 처리하는 TCP 에코 서버이며 Ctrl+C로 종료합니다. 검증에서는 main 전체 바이트 일치, 원본 진입점 보존, 실제 call 대상과 패치 연결, 점프 테이블의 독립 함수 10개를 확인합니다. 포트 오류 4개, 텍스트/UTF-8/128KiB 데이터 에코, 중복 바인딩 오류도 검증하고 테스트 서버를 종료합니다. 소켓 테스트에는 로컬 네트워크 권한이 필요합니다.

결과와 해시는 `output/socket-mode/manifest.json`, `verification.json`에 있습니다. 보존된 GNU build-id는 원본의 값이므로 새 바이너리 식별에는 SHA-256을 사용합니다.

### 최종 심볼 제거 상태

`output/socket-mode/binary`의 `unused_*` 심볼은 모두 제거했습니다. `.symtab`에는 NULL 항목과 `main`(0x401f00, 6,985바이트)만 남습니다. 위 설명의 `unused_N`은 소스·중간 ELF에서 사용하는 이름이며 최종 바이너리에 포함되지 않습니다. `.text.unused` 섹션 이름은 유지합니다. 코드와 실제 점프 테이블은 변경하지 않았으며 기존 버전과 ELF 헤더를 제외한 모든 LOAD 영역 바이트가 같습니다. 재빌드해도 같은 정책을 적용합니다.

검증은 중간 ELF의 주소를 이용해 최종 바이너리의 익명 함수·테이블과 기계어를 검사합니다. main 보존과 로컬 TCP 에코 테스트도 통과했습니다.
