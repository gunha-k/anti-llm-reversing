# Transformation tools

Run these tools from the repository root. Paths are resolved relative to the repository where appropriate.

| Tool | Inputs | Result |
|---|---|---|
| `elf_lab.py` | Cover ELF and optional original executable | Preserved cover with an execution adapter; delegates to the original or embeds the lab echo server |
| `curl_main_hook.py` | Configured curl tree and original `.c/.o/.a` | Same-process dispatch from curl's first main call |
| `native_main_hook.py` | SQLite/Vim/Git archive and original `.c/.o/.a` | Same-process dispatch from an early host function |
| `build.py` | Pinned original `programs/jq` | Three jq symbol/socket variants |
| `mask_socket_strings.py` | Generated socket-router | Equal-length display and environment-name substitutions |
| `build_socket_mode.py` | Pinned original `programs/jq` | Original-main socket-server experiment |

`verify.py`, `verify_native_main_hook.py`, and `verify_socket_mode.py` check their corresponding outputs. `verify_curl_socket.py` and `sanitize_curl_debug_paths.py` are historical utilities for an earlier curl hook and are excluded from the current reproduction workflow.

The assembly, C, and linker files here are implementation helpers. Runnable original examples live in `programs/`. External cover inputs live in `covers/`. Tool-generated results, patches, manifests, and disassembly belong in `output/`.
