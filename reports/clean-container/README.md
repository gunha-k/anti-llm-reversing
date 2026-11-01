# Historical clean Ubuntu container verification

Recorded on 2026-11-01 using Linux x86-64 and Ubuntu 24.04 in Docker. This is a record of an earlier run, not a requirement or instruction to use containers now. Host build/output/jq/object/example products were excluded, and all five external inputs were freshly downloaded over HTTPS and SHA-256 verified.

- `python3 scripts/reproduce.py all --jobs 4` exited 0.
- Three standalone tests passed.
- Nine curl tests passed. The first full run skipped TCP; all nine were rerun successfully with ELF_LAB_NETWORK_TESTS=1 in the same environment. The final reproduction script enables that flag.
- Fourteen generic ELF tests passed, including local TCP checks.
- SQLite/Vim/Git original builds, integrations, structure, invalid ports, echo, SIGTERM, and port conflicts passed (`native-main-hook.json`).
- Each of three jq variants passed 21 comparisons (`jq-variants.json`).
- String substitution and jq socket-mode build/verification passed (`socket-mode.json`).

These are example/structure checks rather than complete upstream suites or universal input compatibility checks. `/workspace` is the historical container path. Report paths describe the layout at the time of the run.
