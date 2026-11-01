# Legacy jq experiments

These experiments use the official, stripped, static jq 1.8.2 Linux amd64 executable at `programs/jq`. Downloads are hash-verified. Address-dependent socket-mode code checks the exact original SHA-256 before patching.

```sh
python3 scripts/reproduce.py legacy
printf '{"items":[1,2,3]}\n' | ./output/socket-router '.items | add'
```

## Symbol and socket-code variants

| Output | Transformation |
|---|---|
| `output/socket-client` | Give eight lowest-address FDE function ranges socket-oriented names; name remaining identified ranges unused_N |
| `output/socket-server` | Add socket syscall code in an RX LOAD below the original mappings and assign socket symbols; retain original entry |
| `output/socket-router` | Add indirect entry and socket dispatch tables; normal dispatch returns to the original jq entry |

The original was stripped. The builder identifies 2,615 ranges through `.eh_frame` FDEs; it does not recover every function or variable. Data symbols describe sections rather than individual variables. Existing-symbol inputs are rejected. Socket symbols come first in the symbol table and by name/address; inserted code is in the first material section, `.text.socket`. Reverse-engineering interfaces may choose their own ordering.

Socket code is assembled from `tools/socket_payload.S`. In variants 2/3 a new RX LOAD starts at `0x3ff000`, with a new mapped program-header table and PT_PHDR. Original LOAD bytes other than the ELF header remain unchanged. Variant 3 preserves initial registers/flags/stack when routing back to jq; read-only socket_mode is 0, so inserted socket syscalls are not executed during normal jq behavior. The inserted fragment is not a complete standalone server. jq strings and control flow remain identifiable.

`tools/verify.py` compares stdout, stderr, and exit status for 21 cases per variant, including Unicode, JSON operations, streaming, regex, arguments, errors, and exit status. It also checks LOAD preservation, symbols, and indirect jumps. Results are saved to `output/verification.json`; hashes are in `output/manifest.json`.

## Equal-length string substitution

`tools/mask_socket_strings.py` copies socket-router to `output/socket-gateway`. In ASCII rodata it replaces jq/JQ with nc/NC, jv/JV with sv/SV, and jqlang.org with socket.org, preserving string lengths, code, and ELF layout. The displayed URL is a label, not an affiliation. The known input changes 291 string runs and 554 bytes. A report with offsets and hashes is written to `output/socket-gateway-strings.json`.

The script verifies 23 cases including user JSON preservation and color settings. Environment names such as JQ_COLORS/JQ_LIBRARY_PATH become NC_*; module and user config paths also change. This variant intentionally changes displayed messages and configuration compatibility. It does not remove every jq fingerprint, built-in filter, or incidental byte string.

## Original-main socket-server variant

`tools/build_socket_mode.py` generates `output/socket-mode/binary`. It preserves entry `0x403a50` and all 6,985 bytes of original main at `0x401f00`. A five-byte jump after ENDBR64 patches its existing callee at `0x407130`, dispatching to the inserted server. The adapter reads argc/argv from the original main's stack. Server termination exits the process rather than returning to jq.

The server uses an indirect state table with ten independent functions for socket/options/bind/listen/accept/read/send/close/error operations. Intermediate symbols use unused_N; the final symbol table retains only main, while `.text.unused` remains. Original bytes outside the ELF header and five-byte callee patch are preserved. GNU build ID remains the original value; use output SHA-256 instead.

```sh
./output/socket-mode/binary         # 127.0.0.1:18080
./output/socket-mode/binary 19090   # override port
python3 tools/verify_socket_mode.py
objdump -d --disassemble=main output/socket-mode/binary
```

This server accepts clients sequentially until interrupted. Verification checks main/entry preservation, the patched call path, ten jump-table targets, final symbols, four invalid ports, ASCII/UTF-8/128 KiB echo, duplicate bind errors, and test-server cleanup. Results and hashes are in `output/socket-mode/manifest.json` and `verification.json`. These offsets are specific to the pinned original.
