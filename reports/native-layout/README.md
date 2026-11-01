# Native layout migration verification

The programs/covers/tools layout was rebuilt on Ubuntu 24.04 x86-64 with Python 3.12.3 and a locally extracted GCC 13 toolchain. No container was used. The full reproduction command exited 0, including all 26 unit tests, all three native hosts with localhost checks, and the jq symbol/string/socket variants. `verification.json` records the command and totals. This is a record of that run, not a substitute for checking future modifications. Current detailed reports remain in the local `output/` directory.
