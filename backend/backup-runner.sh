#!/bin/sh
# Daily Postgres backup runner.
#
# Sleeps until the next BACKUP_HOUR_UTC:00 UTC, then runs pg_dump + gzip into
# $BACKUP_DIR. Prunes anything older than RETENTION_DAYS days.
#
# Loops forever. On startup, sleeps to the NEXT scheduled hour (does not
# back up immediately), so container restarts don't generate noise backups.
#
# Compatible with both BusyBox sh (alpine) and full bash. Avoids `date -d`.

set -eu

RETENTION_DAYS="${RETENTION_DAYS:-30}"
BACKUP_HOUR_UTC="${BACKUP_HOUR_UTC:-3}"
PGHOST="${PGHOST:-postgres}"
PGUSER="${PGUSER:-noodledoc}"
PGDATABASE="${PGDATABASE:-noodledoc}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"

mkdir -p "$BACKUP_DIR"

seconds_until_target_hour() {
    # Compute seconds until the next BACKUP_HOUR_UTC:00:00 UTC using only
    # arithmetic on the current UTC clock. Works on BusyBox `date`.
    cur_h=$(date -u +%H)
    cur_m=$(date -u +%M)
    cur_s=$(date -u +%S)
    # Strip any leading zeros (otherwise `expr` and `$((..))` treat 08/09 as octal)
    cur_h=$(printf '%d' "$cur_h" 2>/dev/null || echo "$cur_h")
    cur_m=$(printf '%d' "$cur_m" 2>/dev/null || echo "$cur_m")
    cur_s=$(printf '%d' "$cur_s" 2>/dev/null || echo "$cur_s")

    secs_now=$(( cur_h * 3600 + cur_m * 60 + cur_s ))
    secs_target=$(( BACKUP_HOUR_UTC * 3600 ))

    if [ "$secs_target" -le "$secs_now" ]; then
        # target already passed today, wait until tomorrow
        echo $(( 86400 - secs_now + secs_target ))
    else
        echo $(( secs_target - secs_now ))
    fi
}

run_backup() {
    ts=$(date -u +%Y%m%d_%H%M%S)
    out="$BACKUP_DIR/noodledoc_${ts}.sql.gz"
    echo "[backup] $(date -u +%FT%TZ) pg_dump → $out"
    if pg_dump -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" | gzip > "$out"; then
        size=$(stat -c %s "$out" 2>/dev/null || wc -c < "$out")
        echo "[backup] success (${size} bytes)"
    else
        echo "[backup] FAILED" >&2
        rm -f "$out"
        return 1
    fi

    # Prune old backups
    find "$BACKUP_DIR" -name 'noodledoc_*.sql.gz' -mtime +"$RETENTION_DAYS" -print -delete 2>/dev/null \
        | while read -r removed; do
            echo "[backup] pruned $removed"
        done
}

echo "[backup] sidecar started; daily backups at ${BACKUP_HOUR_UTC}:00 UTC, ${RETENTION_DAYS}-day retention"

while true; do
    sleep_secs=$(seconds_until_target_hour)
    echo "[backup] sleeping ${sleep_secs}s until next backup window"
    sleep "$sleep_secs"
    run_backup || true
    # avoid double-running within the same minute
    sleep 60
done
