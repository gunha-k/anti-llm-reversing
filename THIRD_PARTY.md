# Third-party inputs

Full external source trees and executables are not committed. `scripts/downloads.json` records pinned HTTPS URLs and SHA-256 values. Preparation downloads cover projects into `covers/` and the working jq executable into `programs/jq`; Git excludes these downloads and generated products.

| Input | Version | Source / license reference |
|---|---|---|
| curl | 8.22.0 | https://curl.se/docs/copyright.html |
| SQLite | 3.50.4 | https://www.sqlite.org/copyright.html |
| Vim | 9.1.0000 | https://github.com/vim/vim/blob/v9.1.0000/LICENSE |
| Git | 2.50.1 | https://github.com/git/git/blob/v2.50.1/COPYING |
| jq official Linux amd64 binary | 1.8.2 | https://github.com/jqlang/jq/releases/tag/jq-1.8.2 |

Retain downloaded copyright and license files. Redistribution of modified binaries must satisfy each project's and linked library's license terms. This document does not replace upstream licenses. A project license for the repository's own code has not been designated.
