#!/bin/bash
# rsync_detector.sh -- detect and alert on unexpected incoming rsync sessions.
#
# Deploy on imagelib. Run from cron every minute:
#   * * * * * /home/nas/flask/imagelib/bin/rsync_detector.sh
#
# Detects rsync --server processes (incoming pushes via SSH), resolves the
# source IP by walking up the process tree to the sshd handler, logs each
# detection, and emails an alert at most once per COOLDOWN seconds per source IP.
#
# Alert email: set RSYNC_DETECTOR_EMAIL or edit ALERT_TO below.
# Cooldown:    set RSYNC_DETECTOR_COOLDOWN or edit COOLDOWN below (seconds).
#
# Expected legitimate sources (not suppressed, but labeled):
#   rfovpn (smart_push.py) -- VPN address, see KNOWN_HOSTS below.
#
# Log: /var/log/rsync_detector.log
# State dir: /var/run/rsync_detector/ (one file per source IP, holds last-alert epoch)

ALERT_TO="${RSYNC_DETECTOR_EMAIL:-gloyer@gmail.com}"
COOLDOWN="${RSYNC_DETECTOR_COOLDOWN:-3600}"
LOG="/var/log/rsync_detector.log"
STATE_DIR="/var/run/rsync_detector"
# VPN IPs of known legitimate rsync sources (space-separated). These are still
# logged but the alert subject will say KNOWN rather than UNKNOWN.
KNOWN_HOSTS="10.74.74.0/24"

mkdir -p "$STATE_DIR"

# ── find rsync --server processes ──────────────────────────────────────────────
RSYNC_PIDS=$(pgrep -f 'rsync --server' 2>/dev/null)
if [ -z "$RSYNC_PIDS" ]; then
    exit 0
fi

TIMESTAMP=$(date -Is)

# ── resolve source IP for each rsync process ────────────────────────────────
declare -A SEEN_IPS   # ip → "known"|"unknown"

resolve_ip() {
    local pid="$1"
    # Walk up: rsync --server → sh -c → sshd handler
    local ppid gpid
    ppid=$(awk '/^PPid:/{print $2}' /proc/"$pid"/status 2>/dev/null) || return
    gpid=$(awk '/^PPid:/{print $2}' /proc/"$ppid"/status 2>/dev/null) || return
    # The sshd handler holds the TCP connection; ss shows it
    ss -tnp 2>/dev/null \
        | awk -v g="$gpid" '
            /pid=/ {
                if (match($0, "pid=" g "[,)]")) {
                    # peer address is field 5 (ESTAB state): [::ffff:a.b.c.d]:port or a.b.c.d:port
                    split($5, addr, ":")
                    # strip IPv4-mapped prefix
                    ip = addr[length(addr)-1]
                    sub(/^\[::ffff:/, "", ip)
                    sub(/\]$/, "", ip)
                    print ip
                    exit
                }
            }'
}

is_known() {
    local ip="$1"
    # Simple CIDR check for 10.74.74.0/24
    if [[ "$ip" =~ ^10\.74\.74\. ]]; then
        echo "known"
    else
        echo "unknown"
    fi
}

for pid in $RSYNC_PIDS; do
    ip=$(resolve_ip "$pid")
    [ -z "$ip" ] && ip="unknown"
    label=$(is_known "$ip")
    SEEN_IPS["$ip"]="$label"
done

# ── log and alert ────────────────────────────────────────────────────────────
NOW=$(date +%s)
NEED_ALERT_IPS=()

for ip in "${!SEEN_IPS[@]}"; do
    label="${SEEN_IPS[$ip]}"
    echo "$TIMESTAMP  rsync from $ip  [$label]" >> "$LOG"

    # Cooldown check
    state_file="$STATE_DIR/$(echo "$ip" | tr '.' '_')"
    if [ -f "$state_file" ]; then
        last_alert=$(cat "$state_file" 2>/dev/null)
        elapsed=$(( NOW - last_alert ))
        [ "$elapsed" -lt "$COOLDOWN" ] && continue
    fi
    NEED_ALERT_IPS+=("$ip ($label)")
    echo "$NOW" > "$state_file"
done

if [ "${#NEED_ALERT_IPS[@]}" -eq 0 ]; then
    exit 0
fi

IP_LIST="${NEED_ALERT_IPS[*]}"

SUBJECT="[imagelib] rsync detected from: $IP_LIST"

BODY="Incoming rsync session(s) detected on imagelib at $TIMESTAMP

Source IPs: $IP_LIST

Active rsync processes:
$(ps -o pid,user,stat,etime,cmd --no-headers -p $RSYNC_PIDS 2>/dev/null)

Recent SSH logins (last 15 min):
$(awk -v d="$(date -d '15 minutes ago' '+%b %e %H:%M' 2>/dev/null || date -v -15M '+%b %e %H:%M' 2>/dev/null)" \
    '\$0 >= d && /Accepted/' /var/log/auth.log 2>/dev/null | tail -20)

Disk usage:
$(df -h /home/nas 2>/dev/null | tail -1)

To investigate:
  ps aux | grep 'rsync --server'
  ss -tnp | grep rsync
  tail -50 /var/log/rsync_detector.log
"

# Try sendmail / mail; fall back to logging only if neither available.
if command -v sendmail &>/dev/null; then
    printf 'To: %s\nSubject: %s\n\n%s\n' "$ALERT_TO" "$SUBJECT" "$BODY" | sendmail -t
elif command -v mail &>/dev/null; then
    echo "$BODY" | mail -s "$SUBJECT" "$ALERT_TO"
else
    echo "$TIMESTAMP  ALERT (no mailer): $SUBJECT" >> "$LOG"
fi

echo "$TIMESTAMP  ALERT sent to $ALERT_TO: $IP_LIST" >> "$LOG"
