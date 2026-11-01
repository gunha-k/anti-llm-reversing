# anti-llm-reversing

A Linux x86-64 lab for preserving one program's behavior while using another project's code, symbols, and debug information as cover material.

## Repository layout

```text
programs/                  Originals that provide the intended behavior
  standalone/              Note editor, small shell, and RLE compressor
  main_hook/               Hello and TCP echo C programs
  jq                       Downloaded, checksum-verified jq executable (untracked)
covers/                    Open-source material used as the visible host
  curl-symbols/            Downloaded curl archive and configured source tree
  native-hosts/downloads/  SQLite, Vim, and Git source archives
  bin/                     Original debug curl executable and license
  catalog.json             Versions, roles, and local paths
tools/                     Transformation and verification implementations
scripts/                   Download, setup, and reproduction entry points
output/                    Generated binaries, patched sources, logs, and manifests
build/                     Temporary compiler and linker products
tests/                     Behavioral and structural checks
docs/                      Tool manuals and reproduction instructions
reports/                   Historical reports, separate from current results
```

`programs/`, `covers/`, and `tools/` separate the working original, the cover material, and the transformation implementation. Generated results belong in `output/`. External downloads and generated files are not committed.

Cover projects are real, functional upstream projects. Their normal application behavior is bypassed in the generated executable. The exact boundary depends on the tool: `elf_lab.py --payload` bypasses the cover entry point, while the main-hook tools enter the cover's main and an early function before dispatching to the original program. Loader initialization and constructors can still run. This layout does not claim that all cover code is unreachable.

## Native installation

Ubuntu 24.04 x86-64 and Python 3.12 or newer are supported. No container is required.

```sh
sudo apt-get update
sudo apt-get install -y python3 build-essential binutils git curl ca-certificates \
  xz-utils pkg-config libssl-dev zlib1g-dev libncurses-dev
python3 scripts/reproduce.py all --jobs 2
```

For the already provisioned workspace, see [LOCAL_SETUP.md](LOCAL_SETUP.md). For a fresh machine, target selection, and generated results, see [reproduction](docs/reproduction.md).

## Use a working executable with a cover

After building curl, run:

```sh
python3 tools/elf_lab.py build covers/bin/curl \
  --payload programs/jq -o output/my-experiment/curl
printf '{"items":[1,2,3]}\n' | ./output/my-experiment/curl '.items | add'
# 6
python3 tools/elf_lab.py verify covers/bin/curl output/my-experiment/curl
```

This mode preserves the cover's code and symbols and executes the original program with `execve`. Keep the original at its recorded absolute path. See the [ELF tool manual](docs/elf-lab.md).

## Link a C program into a cover

```sh
python3 tools/curl_main_hook.py \
  --payload programs/main_hook/hello.c -o output/my-curl
./output/my-curl/curl 'hello from the original main'

python3 tools/native_main_hook.py --host sqlite \
  --payload programs/main_hook/echo.c -o output/my-sqlite
HOOK_ECHO_PORT=19090 ./output/my-sqlite/sqlite3
```

These tools link the original C main into a new executable and call it directly in the same process. C sources, relocatable `.o`, and static `.a` inputs are supported. See the [curl](docs/curl-main-hook.md) and [SQLite/Vim/Git](docs/native-main-hook.md) manuals.

## Existing experiments

The jq symbol, socket-code, string-substitution, and original-main socket experiments remain available through `python3 scripts/reproduce.py legacy`. Their behavior and limitations are described in [legacy experiments](docs/legacy-experiments.md).

Current verification reports are generated under `output/`. Files in `reports/` describe earlier runs and do not certify the current checkout. ELF build IDs may remain unchanged after transformation; use manifest SHA-256 values to identify outputs. The lab tests selected examples and structures, not every possible program or reverse-engineering tool. See [third-party inputs](THIRD_PARTY.md) for upstream versions and license references.
