#!/bin/bash
# rsync_detector.sh -- log incoming rsync sessions with source IP.
#
# Deploy on imagelib. Run from cron every minute:
#   * * * * * /home/nas/flask/imagelib/bin/rsync_detector.sh
#
# Each rsync session is logged once (when first seen), not on every cron tick.
# VPN-sourced connections (10.74.74.x) are labeled [known]; anything else [UNKNOWN].
#
# Log: /var/log/rsync_detector.log
# State dir: /var/run/rsync_detector/ (one file per active rsync PID)

LOG="/var/log/rsync_detector.log"
STATE_DIR="/var/run/rsync_detector"
VPN_SUBNET="10.74.74."

mkdir -p "$STATE_DIR"

RSYNC_PIDS=$(pgrep -f 'rsync --server' 2>/dev/null)
[ -z "$RSYNC_PIDS" ] && exit 0

resolve_ip() {
    local pid="$1"
    local ppid gpid
    ppid=$(awk '/^PPid:/{print $2}' /proc/"$pid"/status 2>/dev/null) || return
    gpid=$(awk '/^PPid:/{print $2}' /proc/"$ppid"/status 2>/dev/null) || return
    ss -tnp 2>/dev/null \
        | awk -v g="$gpid" '
            /pid=/ {
                if (match($0, "pid=" g "[,)]")) {
                    split($5, addr, ":")
                    ip = addr[length(addr)-1]
                    sub(/^\[::ffff:/, "", ip)
                    sub(/\]$/, "", ip)
                    print ip
                    exit
                }
            }'
}

TIMESTAMP=$(date -Is)

for pid in $RSYNC_PIDS; do
    seen_file="$STATE_DIR/pid_$pid"
    [ -f "$seen_file" ] && continue   # already logged this session

    ip=$(resolve_ip "$pid")
    [ -z "$ip" ] && ip="unknown"

    if [[ "$ip" == ${VPN_SUBNET}* ]]; then
        label="known"
    else
        label="UNKNOWN"
    fi

    started=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs)
    echo "$TIMESTAMP  rsync pid=$pid  from=$ip  [$label]  started='$started'" >> "$LOG"
    touch "$seen_file"
done

# Clean up state files for rsync sessions that have ended
for f in "$STATE_DIR"/pid_*; do
    [ -f "$f" ] || continue
    pid="${f##*_}"
    kill -0 "$pid" 2>/dev/null || rm -f "$f"
done
