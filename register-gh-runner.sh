#!/usr/bin/env bash
# register-gh-runner.sh — רשות: המכשיר כ-GitHub self-hosted runner (ריצות חינם, 0 דקות).
# מקור-רשמי: docs.github.com — "Self-hosted runners … Are free to use with GitHub Actions".
# דרישות: PAT עם admin:write (או repo-scope מתאים) ב-$SOVEREIGN_PAT.
set -euo pipefail
REPO="${1:?usage: register-gh-runner.sh <owner/repo> [runner-name]}"
NAME="${2:-sovereign-device-$(hostname)}"
: "${SOVEREIGN_PAT:?SOVEREIGN_PAT env required (never committed)}"
DIR=/opt/sovereign/gh-runner
mkdir -p "$DIR" && cd "$DIR"
ARCH=$(uname -m); [ "$ARCH" = "x86_64" ] && A=arm64-x64 && A=x64 || A=arm64
VER=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | grep -o '"tag_name": *"v[^"]*"' | cut -d'"' -f4 | sed 's/v//')
echo "[runner] latest runner version: $VER"
[ -f config.sh ] || { curl -sL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-linux-${A}-${VER}.tar.gz"; tar xzf runner.tar.gz; }
TOKEN=$(curl -s -X POST -H "authorization: Bearer ${SOVEREIGN_PAT}" -H "accept: application/vnd.github+json" \
  "https://api.github.com/repos/${REPO}/actions/runners/registration-token" | grep -o '"token": *"[^"]*"' | cut -d'"' -f4)
[ -n "$TOKEN" ] || { echo "[runner] token fetch failed — honest fail"; exit 1; }
./config.sh --url "https://github.com/${REPO}" --token "$TOKEN" --name "$NAME" --labels sovereign-device --unattended --replace
sudo ./svc.sh install && sudo ./svc.sh start
echo "[runner] registered + service started — workflows with runs-on: [self-hosted, sovereign-device] now run on THIS hardware at zero minutes"
