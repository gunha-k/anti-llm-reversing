# Open-source cover material

This directory holds the upstream material whose code, symbols, strings, and debug information provide the generated executable's visible host.

| Project | Version | Local input |
|---|---|---|
| curl | 8.22.0 | `curl-symbols/curl-8.22.0.tar.xz` and configured `curl-symbols/curl-8.22.0/` |
| SQLite | 3.50.4 | `native-hosts/downloads/sqlite-autoconf-3500400.tar.gz` |
| Vim | 9.1.0000 | `native-hosts/downloads/vim-9.1.0000.tar.gz` |
| Git | 2.50.1 | `native-hosts/downloads/git-2.50.1.tar.xz` |

Run `python3 scripts/reproduce.py fetch` to download the archives and the original jq program. `curl` or `all` configures/builds the curl source tree and writes the original debug executable to `covers/bin/curl`. Native tools extract working source copies under `output/native-main-hook/HOST/work/`; the downloaded archives remain unchanged here.

These projects work normally upstream. Their ordinary application functionality is bypassed in transformed outputs; the main-hook methods still execute an early host path and share loader initialization. See each tool manual for the precise execution boundary.

`catalog.json` records the roles and paths. Pinned URLs and SHA-256 values live in `scripts/downloads.json`. Downloaded projects, their licenses, and generated cover binaries remain local and are ignored by Git. Do not put the behavior-providing original in this folder, and do not write final transformed binaries here.
