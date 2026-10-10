#!/bin/sh
# Container entrypoint. If a persistent disk is mounted at $DATA_DIR (Render: /var/data), keep data/ on it so chats,
# orders and plans survive restarts and redeploys. The first boot seeds the disk with the repo's data/ folder.
set -e
cd /app
if [ -n "$DATA_DIR" ]; then
  mkdir -p "$DATA_DIR"
  if [ ! -e "$DATA_DIR/data" ]; then
    echo "Seeding $DATA_DIR/data from the image"
    cp -a /app/data "$DATA_DIR/data"
  fi
  rm -rf /app/data
  ln -s "$DATA_DIR/data" /app/data
fi
if [ -z "$CODEBUDDY_API_KEY" ]; then
  echo "WARNING: CODEBUDDY_API_KEY is not set — the agent cannot log in."
fi
exec python console/server.py
