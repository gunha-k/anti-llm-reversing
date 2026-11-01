# Native reproduction

## Requirements

Use Ubuntu 24.04 x86-64, Python 3.12 or newer, GCC, GNU make/binutils, curl, xz, pkg-config, and OpenSSL/zlib/ncurses development headers. Install them using the README commands. Preparation scripts do not invoke sudo or install system packages. Use a repository path without spaces or shell metacharacters.

```sh
python3 scripts/reproduce.py all --jobs 2
```

The workflow verifies each external download against `scripts/downloads.json`, compiles the programs and covers, creates transformed executables, and checks behavior and ELF structure. Local TCP tests use temporary ports on `127.0.0.1`. Initial downloads require Internet access. Builds can take several minutes.

## Targets

| Target | Scope |
|---|---|
| `standalone` | Build and test note, minish, and rle in `programs/standalone` |
| `fetch` | Download and checksum all five external inputs |
| `curl` | Build debug curl in `covers/`, link hello/echo, and run integration tests |
| `native` | Build SQLite/Vim/Git with echo and compare structure and TCP behavior |
| `legacy` | Build and verify jq symbol, string, and socket experiments |
| `all` | All builds and checks, including generic ELF network tests |

`--jobs N` controls build concurrency. `--deps /absolute/root` selects the root containing `usr/include/ncurses.h` and development libraries; the default is `/`. For the local extracted development packages use `.local/sysroot` as documented in `LOCAL_SETUP.md`.

## Input and output locations

Working originals live in `programs/`. Open-source cover downloads and the baseline curl build live in `covers/`. Transformation implementations live in `tools/`; generated executables and reports live in `output/`. Native projects use separate patched working source trees beneath their output directories. Compiler intermediates also use `build/`.

Downloads are reused only if their checksum matches. Existing transformed output directories and existing configured curl trees cause the corresponding builder to stop rather than overwrite them. Run `all`, `curl`, or `native` in a fresh workspace. Preserve prior results before preparing a clean build; simply rerunning `all` after success is not a verification command.

## Recheck an existing build

```sh
python3 -m unittest discover -s tests -p test_standalone.py -v
ELF_LAB_NETWORK_TESTS=1 python3 -m unittest discover -s tests -p test_curl_main_hook.py -v
python3 tools/verify_native_main_hook.py --network
python3 tools/verify.py
python3 tools/verify_socket_mode.py
ELF_LAB_NETWORK_TESTS=1 python3 -m unittest discover -s tests -p test_elf_lab.py -v
```

`mask_socket_strings.py` both generates and verifies its variant. `verify_curl_socket.py` and `sanitize_curl_debug_paths.py` target a historical hook and are not part of this workflow. Current `output/curl-socket/curl` uses `HOOK_ECHO_PORT`.

External versions and hashes are fixed, but system/compiler versions are not. Output hashes and symbol addresses can differ from historical reports. Checks cover documented structures and examples, not the entire upstream test suites or all user programs. Linux ELF outputs need compatible x86-64 Linux runtimes.
