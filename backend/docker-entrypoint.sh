#!/bin/sh
# Container entrypoint that fixes ownership on mounted volumes before
# dropping privileges to the unprivileged "app" user.
#
# Named Docker volumes are root-owned on first create, so a non-root
# container user cannot write to them. We chown here as root, then
# exec the real command via gosu/su-exec/setpriv (whichever is available).

set -e

DATA_DIRS="/data/edi"

if [ "$(id -u)" = "0" ]; then
    for dir in $DATA_DIRS; do
        if [ -d "$dir" ]; then
            # Only chown if not already owned by app
            current_uid=$(stat -c "%u" "$dir" 2>/dev/null || echo "0")
            if [ "$current_uid" != "10001" ]; then
                echo "[entrypoint] chown app:app $dir"
                chown -R app:app "$dir" || echo "[entrypoint] chown failed (continuing)"
            fi
        fi
    done

    # Drop privileges and exec the real command. Try setpriv (util-linux,
    # always present in Debian-based images), falling back to su.
    # We force HOME=/home/app so libraries that read ~/.foo don't hit /root.
    if command -v setpriv >/dev/null 2>&1; then
        exec env HOME=/home/app setpriv --reuid=app --regid=app --init-groups "$@"
    else
        exec env HOME=/home/app su -s /bin/sh app -c "$*"
    fi
else
    # Already non-root, just exec
    exec "$@"
fi
