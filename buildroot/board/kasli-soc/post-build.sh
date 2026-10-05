#!/bin/sh
set -eu
board=$(dirname "$0")
project=$(realpath "$board/../../..")
install -D -m 0644 "$board/extlinux.conf" "$BINARIES_DIR/extlinux.conf"
install -D -m 0644 "$project/build/gateware/csr.json" "$TARGET_DIR/etc/litex/csr.json"
install -D -m 0755 "$project/tools/pl_test.py" "$TARGET_DIR/usr/bin/pl_test.py"
install -D -m 0755 "$project/tools/dump_ps7_state.py" "$TARGET_DIR/usr/bin/dump_ps7_state.py"
install -D -m 0600 "$project/build/ssh/id_ed25519.pub" "$TARGET_DIR/root/.ssh/authorized_keys"
chmod 0700 "$TARGET_DIR/root/.ssh"
