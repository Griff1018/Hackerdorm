# BizFlow Agent Console — one container: the Python console server + the CodeBuddy (WorkBuddy) CLI it drives.
# Deploy on Render as a Docker web service (see render.yaml / docs/DEPLOY_RENDER.md).
FROM python:3.13-slim-bookworm

# Node.js 20 (the CodeBuddy CLI needs Node >= 18.20; Debian's own nodejs is too old)
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && apt-get update && apt-get install -y --no-install-recommends git ripgrep ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @tencent-ai/codebuddy-code \
 && codebuddy --version

WORKDIR /app
COPY . .

# Listen on all interfaces; Render supplies PORT. The agent runs `python -m app.bizflow_cli …`, so `python` must exist (it does here).
ENV BIZFLOW_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8

CMD ["sh", "deploy/start.sh"]
