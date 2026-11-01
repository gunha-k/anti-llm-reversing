# curl main의 첫 함수에 매크로를 넣는 도구

`src/curl_main_hook.py`는 기존 `src/elf_lab.py`와 독립된 도구입니다.
실행할 프로그램의 C 소스, relocatable `.o`, 정적 `.a`를 curl과 함께 링크하여
하나의 실행 파일을 만듭니다. 기존 자동화 도구, 원본 curl 실행 파일,
기존 curl 소스·오브젝트는 변경하지 않습니다.

## 실행 경로

```text
ELF 로더 / C 런타임 초기화
  → curl의 main(argc, argv)
  → tool_init_stderr(argc, argv)       ← main의 첫 함수 호출
  → CURL_DISPATCH_REAL_MAIN 매크로
  → curl_hook_real_main(argc, argv)   ← 입력 프로그램의 원래 main
  → exit(실제 main의 반환값)
```

이 curl 소스에서 `tool_init_stderr()`보다 앞에는 지역 변수 `result`의 초기값
대입만 있습니다. 훅은 stderr 대입, `main_checkfds()`, SIGPIPE 설정,
메모리 추적 초기화, `globalconf_init()` 및 `operate()`보다 먼저 실행됩니다.

두 인자를 받는 main에 대한 생성 매크로는 다음과 같습니다.

```c
extern int curl_hook_real_main(int argc, char **argv);
#define CURL_DISPATCH_REAL_MAIN(argc, argv) \
  do { exit(curl_hook_real_main((argc), (argv))); } while(0)
```

매크로 자체는 별도 실행 함수가 아닙니다. 컴파일된 `tool_init_stderr`는 실제 main을
직접 `call`하고, 반환값을 `exit`에 전달합니다. `exit`는 프로세스의 정상 종료를 처리하여
stdio flush, `atexit`, 소멸자가 실행되도록 합니다. 실제 main이 `exit`를 직접 호출하거나
신호로 종료하면 그 동작이 적용됩니다. 새 프로세스 생성, `execve`, `dlopen` 기반 실행기를
추가하지 않습니다. 입력 프로그램 자체가 호출하는 함수까지 금지·제거하는 기능은 아닙니다.

## 빌드

요구 환경은 Linux x86-64, Python 3, GCC, GNU make와 binutils입니다.
구성·빌드를 완료한 curl 트리와 정적 libcurl 아카이브가 필요합니다. 기본 트리는
`build/curl-symbols/curl-8.22.0`입니다. 네트워크 다운로드는 하지 않습니다.

```sh
# C 소스: int main(int argc, char **argv)
python3 src/curl_main_hook.py \
  --payload examples/main_hook/hello.c -o output/my-hook
./output/my-hook/curl '원래 프로그램의 인자' '두 번째 인자'

# 기존 오브젝트 / 정적 라이브러리도 가능
python3 src/curl_main_hook.py --payload /path/program.o -o output/object-hook
python3 src/curl_main_hook.py --payload /path/program.a -o output/archive-hook

# 여러 소스 및 추가 빌드 옵션
python3 src/curl_main_hook.py \
  --payload /path/main.c /path/helper.c /path/support.a \
  --payload-cflag=-I/path/include --payload-ldflag=-lm \
  -o output/multi-hook
```

모든 입력을 합쳐 외부에 노출된 `main` 정의가 정확히 하나 있어야 합니다.
각 입력의 복사본에 `objcopy --redefine-sym main=curl_hook_real_main`을 적용합니다.
다른 번역 단위에서 main을 참조하는 경우도 함께 변경됩니다. 원본 입력은 보존합니다.
`curl_hook_real_main` 이름은 도구가 예약합니다.

main 시그니처는 명시적으로 지정합니다. 오브젝트 심볼 테이블만으로는 함수 인자 형식을
알 수 없으므로 도구가 자동 추측하지 않습니다.

| 원본 main 정의 | 옵션 |
|---|---|
| `int main(int argc, char **argv)` | 기본값, `--main-arity 2` |
| `int main(void)` | `--main-arity 0` |
| `int main(int argc, char **argv, char **envp)` | `--main-arity 3` |

`--main-arity 3`은 현재 `environ`을 세 번째 인자로 전달합니다.
C 소스는 디버그 정보와 PIC를 포함하여 컴파일합니다. `.o/.a`는 네이티브 ABI와
curl의 링크 방식에 맞아야 합니다. 필요하면 `-fPIC`로 다시 컴파일하세요.
완성된 ELF 실행 파일은 입력으로 받지 않습니다. C++ 런타임, LTO 오브젝트,
특수 언어 런타임을 일반적으로 처리하는 도구는 아닙니다.

다른 curl 트리는 `--curl-tree /path/to/configured-curl`로 지정합니다.
이 도구는 `tool_main`과 `tool_stderr`가 별도 오브젝트인 빌드를 지원합니다.
함수 구조가 다르거나 이미 훅이 있는 소스는 명확한 오류로 중단합니다.
기본 트리에서는 같은 폴더의 `curl-8.22.0.tar.xz`에서 수정 전 소스 3개를 읽습니다.
`--source-archive /path/curl.tar.xz`로 명시할 수도 있습니다.
아카이브 전체를 추출하거나 기존 트리의 소스를 덮어쓰지 않습니다.

## TCP 에코 예제

```sh
python3 src/curl_main_hook.py \
  --payload examples/main_hook/echo.c -o output/my-echo-hook
HOOK_ECHO_PORT=19090 ./output/my-echo-hook/curl
```

`127.0.0.1`에서 한 연결을 처리하고 EOF 후 종료합니다. 기본 포트는 18080입니다.
이는 예제 프로그램의 동작이며 자동화 도구가 입력 프로그램에 강제하는 동작이 아닙니다.
생성한 `curl`은 입력 `.c/.o/.a` 또는 별도 원본 실행 파일 없이 실행할 수 있습니다.
링크된 공유 라이브러리와 입력 프로그램의 외부 리소스는 계속 필요합니다.

## 결과물과 검증

출력 디렉터리에는 다음 항목이 생성됩니다. 기존 경로에는 덮어쓰지 않습니다.
빌드 실패 시 진단용 로그와 중간 파일을 남깁니다.

- `curl`: 실행 파일. curl 및 실제 main의 심볼과 디버그 정보를 포함합니다.
- `sources/`: 패치된 curl 파일 3개와 매크로 헤더.
- `objects/`: 새 curl 오브젝트 2개와 main을 이름 변경한 입력 오브젝트.
- `curl-main-hook.patch`: 수정 전 curl 소스에 대한 패치.
- `manifest.json`, `build.log`, `symbols.txt`: 해시·옵션·검증·빌드 기록.
- `*.disassembly.txt`: curl main, 첫 함수, 실제 main의 디스어셈블리.

빌드 시 실제 기계어를 검사하여 main의 첫 `call`이 `tool_init_stderr`인지,
그 함수가 실제 main을 직접 호출하고 `exit`로 종료하는지 확인합니다.
원본 curl 오브젝트의 공개 심볼 유지와 기존 curl 소스·오브젝트의 해시도 검사합니다.
재링크되므로 함수 주소와 main의 기계어가 이전 curl과 바이트 단위로 같지는 않습니다.

```sh
python3 -m unittest discover -s tests -p test_curl_main_hook.py -v
ELF_LAB_NETWORK_TESTS=1 python3 -m unittest discover -s tests -p test_curl_main_hook.py -v
```

테스트는 C·`.o`·`.a`, 여러 소스와 링크 옵션, main 인자 0·2·3개,
인자·환경·현재 디렉터리·바이너리 표준입출력·반환값·신호 종료를 검사합니다.
`atexit` 및 소멸자, 초기 SIGPIPE 상태, 닫힌 stdin 유지도 원본과 비교합니다.
실행 중 PID와 `/proc/self/exe`가 생성한 프로세스·바이너리를 가리키는지도 확인합니다.
네트워크 옵션을 켜면 원본/통합 에코 프로그램에서 빈 데이터·UTF-8·128 KiB 데이터를 비교합니다.

## 동작 동일성의 범위

입력 main에 진입하기 전에 curl main 내부의 초기화가 실행되지 않도록 합니다.
ELF 로더, 공유 라이브러리 초기화, `.init_array` 생성자는 main보다 먼저 실행됩니다.
통합 파일은 이들 런타임을 공유하므로 두 독립 실행 파일의 동작이 모든 조건에서
완전히 같다고 보장할 수는 없습니다.

인자와 환경은 받은 그대로 전달합니다. `argv[0]` 및 `/proc/self/exe`는 통합 바이너리를
가리키므로, 파일 이름이나 실행 파일 주변 리소스에 의존하는 프로그램에는 조정이 필요합니다.
스택 추적에는 curl main과 초기 함수가 추가되며, 프로세스 전체 심볼 충돌·생성자 간섭이
있는 입력도 별도 통합 작업이 필요합니다. 테스트의 출력 비교는 같은 `argv[0]`을 사용합니다.
