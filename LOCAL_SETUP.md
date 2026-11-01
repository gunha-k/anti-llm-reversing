# Native setup in this workspace

Workspace: `/home/arag5/llm-misleading`. Original upstream baseline: `9cadd5aa7f0c56fb8315048018b1c7e64463cc8d` of https://github.com/gunha-k/anti-llm-reversing.

Ubuntu 24.04 x86-64 and Python 3.12.3 run directly on the host. No container is used. Because system package installation requires a sudo password, GCC 13, make, pkgconf, and development headers were extracted from official Ubuntu deb packages into `.local/sysroot`. Package versions/hashes are recorded in `scripts/local-packages.json`; cached packages are in `.local/debs`. Runtime libraries are provided by the host. This setup references host runtime paths and is not a portable bundle for other operating systems.

```bash
cd /home/arag5/llm-misleading
source scripts/activate.sh
./programs/standalone/minish -c 'printf hello'
printf '{"items":[1,2,3]}\n' | ./output/socket-router '.items | add'
./output/curl-main-hook/hello/curl 'hello from the original main'
HOOK_ECHO_PORT=19090 ./output/native-main-hook/git/git
```

The last command runs the echo server in the foreground; stop it with Ctrl+C. Connect from another terminal to 127.0.0.1:19090.

```bash
./scripts/reproduce-local.sh standalone
./scripts/reproduce-local.sh fetch
```

For a clean initial full build use `./scripts/reproduce-local.sh all`. Existing configured curl trees and transformation output directories are intentionally rejected, so do not rerun all/curl/native over completed products. See [reproduction](docs/reproduction.md) for individual verification commands; source the activation script first.

Previous-layout results and the old curl tree are retained locally in `.local/previous-output` and `.local/previous-curl-tree`. New-layout build output is in `.local/restructure-build.log`. Current JSON reports are in `output/`; `reports/` contains historical evidence. External input versions and hashes remain unchanged by the layout migration.
