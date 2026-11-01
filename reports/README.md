# Verification records

`clean-container/` records an earlier reproduction in a clean Ubuntu container. It is historical evidence, not the setup used by the current native workspace.

`historical/` contains JSON reports from earlier local experiments. Absolute workspace paths were replaced with `<workspace>`; ELF hashes and measurements retain their recorded values. These files do not claim that the current checkout was reverified.

New reports are generated in `output/` by `python3 scripts/reproduce.py all`. The new layout uses `programs/`, `covers/`, and `tools/`; historical reports can still mention the old layout.
