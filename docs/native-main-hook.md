# SQLite · Vim · Git의 초기 함수에서 실제 main 호출

기존 `elf_lab.py` 및 `curl_main_hook.py`를 수정하지 않고 별도로 만든 도구입니다.
각 프로젝트를 원본 소스에서 빌드한 다음, 같은 프로세스에서 입력 프로그램의 main을
직접 호출하도록 초기 함수에 매크로를 추가합니다.

## 생성된 결과

| 호스트 | 버전 | 실행 파일 | 디버그 포함 크기 | 원본 공개 심볼 → 결과 공개 심볼 |
|---|---|---|---|---|
| SQLite | 3.50.4 | `output/native-main-hook/sqlite/sqlite3` | 약 2.91 MiB | 334 → 337 |
| Vim | 9.1.0000 | `output/native-main-hook/vim/vim` | 약 10.90 MiB | 6,358 → 6,361 |
| Git | 2.50.1 | `output/native-main-hook/git/git` | 약 13.83 MiB | 3,202 → 3,205 |

공개 심볼 수는 해당 빌드의 정의된 외부 심볼을 중복 이름 없이 센 값이며,
함수뿐 아니라 전역 데이터 심볼을 포함합니다. 세 결과 모두 원본 공개 심볼의 이름을
보존했고 `main`, 실제 main, 프로젝트별 대표 함수와 `.symtab`, `.debug_info`를 확인했습니다.
재링크되므로 원본과 주소 또는 기계어 바이트가 동일하다는 뜻은 아닙니다.

현재 샘플의 실제 동작은 `examples/main_hook/echo.c`의 로컬 TCP 에코 서버입니다.
`HOOK_ECHO_PORT`로 포트를 지정하며 기본 주소는 `127.0.0.1:18080`입니다.
한 클라이언트가 송신을 종료하면 데이터를 모두 반환하고 정상 종료합니다.
`--version`을 포함한 명령행 인자도 실제 프로그램에 그대로 전달되므로, 이 샘플에서는
원래 호스트의 버전 출력을 실행하지 않습니다.

```sh
HOOK_ECHO_PORT=19090 ./output/native-main-hook/sqlite/sqlite3
HOOK_ECHO_PORT=19091 ./output/native-main-hook/vim/vim
HOOK_ECHO_PORT=19092 ./output/native-main-hook/git/git
```

각 폴더의 `sqlite3.original`, `vim.original`, `git.original`은 훅 적용 전 빌드입니다.
각 원본의 버전 출력도 확인하고 매니페스트에 기록했습니다.

## 전환 위치

| 호스트 | 경로 | 전환 전에 실행하지 않는 호스트 초기화 |
|---|---|---|
| SQLite | `main → main_init → 실제 main` | stderr 버퍼 변경, isatty 검사, 시그널 핸들러, SQLite 설정 |
| Vim | `main → mch_early_init → 실제 main` | 스택 검사·시그널 대체 스택, 터미널·사용자 설정 초기화 |
| Git | `main → init_git → 실제 main` | trace2, 표준 FD 복구, SIGPIPE 변경, locale 및 repository 초기화 |

SQLite의 `main_init`은 원래 초기 main 작업 뒤에 있었으므로, 첫 libc 호출인 `setvbuf`
앞으로 이동했습니다. Vim과 Git은 원래 첫 함수 호출 위치를 사용합니다.

호스트 함수의 기존 시그니처는 유지합니다. main에서 첫 함수 호출 직전에 `argc/argv`를
전용 전역 변수 두 개에 저장합니다. 이 저장은 추가 함수나 생성자를 호출하지 않습니다.
첫 함수 내부에서는 다음 매크로가 실행됩니다.

```c
#define NATIVE_MAIN_DISPATCH() \
  do { (exit)(native_hook_real_main(native_hook_argc, native_hook_argv)); } while (0)
```

`exit`는 반환값으로 정상 종료하고 stdio flush 및 atexit 처리를 수행합니다.
Git이 자체 정의한 함수형 `exit(...)` 매크로는 `(exit)(...)` 표기로 우회하여
초기화되지 않은 Git의 `common_exit`나 trace2 경로로 들어가지 않습니다.

검증은 **전환 함수의 실제 call 대상**이 `native_hook_real_main`, `exit@plt` 두 개인지
확인합니다. Git·Vim의 원래 프로세스 실행 관련 코드는 유지하며, 실행 파일 전체에서
`execve` 등의 심볼을 제거하거나 금지하지 않습니다.

## 재빌드

Linux x86-64, Python 3.12 이상, GCC, GNU make 및 binutils가 필요합니다.
입력 프로그램은 C 소스 또는 네이티브 relocatable `.o` / 정적 `.a`여야 합니다.
입력을 합쳤을 때 전역 main 정의가 정확히 하나 있어야 합니다.

```sh
python3 src/native_main_hook.py --host sqlite \
  --payload /path/main.c /path/helper.c -o output/my-sqlite

python3 src/native_main_hook.py --host vim \
  --payload /path/program.o --payload-ldflag=-lm -o output/my-vim

python3 src/native_main_hook.py --host git \
  --payload /path/program.a --main-arity 3 -o output/my-git
```

- `--main-arity 2`: 기본값, `int main(int, char **)`.
- `--main-arity 0`: `int main(void)`.
- `--main-arity 3`: `int main(int, char **, char **)`, 세 번째 인자는 `environ`.
- `--payload-cflag`: C 소스 컴파일 옵션. `--payload-cflag=-I/path/include`처럼 전달합니다.
- `--payload-ldflag`: 최종 링크 옵션. 여러 번 지정할 수 있습니다.
- `--jobs`: 각 native make의 작업 수. 기본 2.
- `--downloads`, `--deps`: 소스 아카이브 및 로컬 개발 패키지 경로 변경.

`.a`는 `--whole-archive`로 relocatable 오브젝트에 합칩니다. 사용하지 않는 멤버의
추가 의존성까지 필요할 수 있으므로, 일반적인 외부 의존 라이브러리는
`--payload-ldflag`로 링크하는 편이 적합합니다. C++/다른 언어 런타임, LTO 오브젝트,
완성된 ELF 실행 파일은 지원 범위가 아닙니다. main 인자 형식은 자동 추측하지 않습니다.

출력 디렉터리는 새 경로여야 합니다. native Makefile 제약 때문에 출력 경로에는
공백이나 셸 특수문자를 허용하지 않습니다. 실패한 빌드의 로그와 중간 결과는 남습니다.
실행 결과에는 입력 소스·오브젝트 파일이 필요 없지만, 공유 라이브러리 및 실제
프로그램이 사용하는 외부 리소스는 계속 필요합니다.

## 소스 및 빌드 구성

최신 버전 자동 추종 대신 다음 배포본을 고정했으며 다운로드 파일의 SHA-256을
빌드 전에 검사합니다. URL과 해시는 `src/native_main_hook.py` 및 각 매니페스트에 있습니다.

- [SQLite 공식 3.50.4 배포본](https://www.sqlite.org/2025/sqlite-autoconf-3500400.tar.gz)
- [Vim 공식 저장소 v9.1.0000](https://github.com/vim/vim/releases/tag/v9.1.0000)
- [Git 공식 2.50.1 배포본](https://www.kernel.org/pub/software/scm/git/git-2.50.1.tar.xz)

아카이브는 현재 `build/native-hosts/downloads/`에 있습니다. 깨끗한 작업 공간에서는:

```sh
mkdir -p build/native-hosts/downloads
curl -fL https://www.sqlite.org/2025/sqlite-autoconf-3500400.tar.gz \
  -o build/native-hosts/downloads/sqlite-autoconf-3500400.tar.gz
curl -fL https://codeload.github.com/vim/vim/tar.gz/refs/tags/v9.1.0000 \
  -o build/native-hosts/downloads/vim-9.1.0000.tar.gz
curl -fL https://www.kernel.org/pub/software/scm/git/git-2.50.1.tar.xz \
  -o build/native-hosts/downloads/git-2.50.1.tar.xz
```

Vim을 위해 Ubuntu 24.04의 `libncurses-dev` 6.4+20240113-1ubuntu2.2 패키지를
`build/native-hosts/deps`에 추출했습니다. 시스템에 패키지를 설치하지 않았습니다.
다시 준비하려면 다운로드 폴더에서 `apt-get download libncurses-dev`를 실행하고,
받은 `.deb`를 `dpkg-deb -x PACKAGE.deb /absolute/path/to/build/native-hosts/deps`로 추출합니다.
현재 스크립트는 x86-64 경로의 시스템 `libtinfo.so.6`를 사용합니다.

모든 호스트는 `-O0 -g3 -fno-inline -fno-omit-frame-pointer -fno-lto`와
`--no-gc-sections`를 사용합니다. 호스트별 구성은 다음과 같습니다.

- SQLite: 배포본의 shell.c와 sqlite3.c를 직접 컴파일합니다. readline 없는 CLI입니다.
- Vim: huge 기능 구성, 터미널 버전입니다. GUI·X11·NLS·GPM·SELinux·XSMP는 비활성화했습니다.
- Git: Git 본체를 빌드합니다. curl/OpenSSL/expat/gettext/Perl/TclTk 선택 기능은 비활성화했습니다.
  Git의 일반 프로세스 실행 관련 함수는 남습니다.

각 원본과 결과는 이 구성의 바이너리이며, 배포판 기본 바이너리의 모든 선택 기능을
포함한다는 뜻은 아닙니다. 프로젝트 라이선스와 원본 소스는 각 `work/` 트리에 보존됩니다.

## 결과 파일과 검증

각 호스트 폴더에는 실행 파일과 `.original`, `manifest.json`, `symbols.txt`,
`main-hook.patch`, `sources/`, `payload/`, `work/`, `build.log`,
`main`·초기 함수·실제 main의 디스어셈블리가 있습니다.

```sh
# 구조 및 네트워크를 사용하지 않는 오류 동작 비교
python3 src/verify_native_main_hook.py

# 실제 로컬 에코, 실행 파일·프로세스 유지 및 종료까지 비교
python3 src/verify_native_main_hook.py --network
```

이 검증기는 포함된 echo.c 샘플용이며 매니페스트의 입력 해시를 확인합니다.
다른 프로그램의 모든 동작을 자동으로 판단하는 검증기는 아닙니다.

세 결과 각각 다음 항목을 통과했습니다.

- main의 첫 호출과 직접 전환 경로, 디버그 정보 및 원본 공개 심볼 유지.
- 잘못된 포트 6개에 대한 원본과 stdout·stderr·종료 코드 일치.
- 빈 데이터, ASCII, UTF-8, 128 KiB 이진 데이터의 원본과 동일한 에코 및 EOF 종료.
- 에코 동작 중 `/proc/PID/exe`가 생성한 바이너리를 가리키며 자식 프로세스가 없음.
- SIGTERM 종료 및 포트 충돌 시 실패 동작.

전체 결과는 `output/native-main-hook/verification.json`에 기록했습니다.
네트워크 옵션 없이 다시 실행하면 해당 파일에는 네트워크 검증이 `not_run`으로 기록됩니다.
SQLite·Vim·Git의 전체 upstream 테스트 스위트를 실행한 것은 아닙니다.

ELF 및 공유 라이브러리 생성자는 main보다 먼저 실행됩니다. 두 프로그램을 링크하므로
심볼 충돌, 생성자 간섭, argv[0]·실행 파일 경로·주변 리소스에 의존하는 동작은
별도 통합 검토가 필요합니다. 예제에서 확인한 동작 일치가 모든 입력의 완전한 동일성을
보장하지는 않습니다.
