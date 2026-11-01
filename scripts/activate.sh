# Source from bash: source scripts/activate.sh
_LAB_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$_LAB_ROOT/.local/bin:$PATH"
export LD_LIBRARY_PATH="$_LAB_ROOT/.local/sysroot/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PKG_CONFIG_SYSROOT_DIR="$_LAB_ROOT/.local/sysroot"
export PKG_CONFIG_LIBDIR="$_LAB_ROOT/.local/sysroot/usr/lib/x86_64-linux-gnu/pkgconfig:$_LAB_ROOT/.local/sysroot/usr/share/pkgconfig"
unset _LAB_ROOT
