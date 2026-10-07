#!/bin/sh
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"
UMASK_VAL="${UMASK:-0000}"

# Ensure group exists
if ! getent group "$PGID" >/dev/null 2>&1; then
  groupadd -g "$PGID" simposter >/dev/null 2>&1 || true
fi

# Ensure user exists and is in group
if ! getent passwd "$PUID" >/dev/null 2>&1; then
  useradd -u "$PUID" -g "$PGID" -d /app -s /usr/sbin/nologin simposter >/dev/null 2>&1 || true
else
  usermod -g "$PGID" "$(getent passwd "$PUID" | cut -d: -f1)" >/dev/null 2>&1 || true
fi

# Set requested umask (default 0002 -> files 664, dirs 775)
umask "$UMASK_VAL"

# Ensure the settings folder and DB file exist BEFORE fixing ownership below.
# (Creating them after the chown -- as this script used to -- left a brand-new
# folder/DB owned by root, so the app, running as PUID, crashed on first start
# with "attempt to write a readonly database"; a restart then fixed it.)
DB_FILE="/config/settings/simposter.db"
mkdir -p /config/settings
if [ ! -f "$DB_FILE" ]; then
  touch "$DB_FILE" || true
fi
chmod 0644 "$DB_FILE" || true

# Ensure ownership on writable paths
chown -R "$PUID:$PGID" /config /app >/dev/null 2>&1 || true

# Drop privileges and exec
exec gosu "$PUID:$PGID" "$@"
