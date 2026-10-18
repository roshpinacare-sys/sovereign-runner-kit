#!/usr/bin/env bash
# sovereign-runner-register — turn ANY machine the owner controls into a free fleet runner.
# Zero-cost law: self-hosted runners consume NO Actions minutes. Private-repo lanes that
# declare `runs-on: [self-hosted, sovereign]` QUEUE until a sovereign runner connects —
# "waiting for sovereign capacity" instead of the private-minutes instant-fail.
#
# Usage (one command, from the machine's shell):
#   SOVEREIGN_PAT=<fine-grained PAT with repo Administration:write> \
#     ./sovereign-runner-register.sh [labels...]
# or with a runner registration token obtained from the repo UI:
#   RUNNER_TOKEN=<token> ./sovereign-runner-register.sh [labels...]
#
# What it does: fetches a registration token (if a PAT is given) -> downloads the runner
# -> configures with labels "sovereign,<labels>" -> installs a system service that
# survives reboots. Idempotent: re-running reconfigures in place.
set -euo pipefail

ORG=roshpinacare-sys
REPO="${SOVEREIGN_RUNNER_REPO:-sovereign-executor}"
RUNNER_DIR="${SOVEREIGN_RUNNER_DIR:-$HOME/sovereign-runner}"
LABELS="sovereign${1:+,$1}"

need() { command -v "$1" >/dev/null || { echo "missing dependency: $1"; exit 2; }; }
need curl; need tar

api() { curl -s -H "Authorization: Bearer ${SOVEREIGN_PAT:-}" -H "Accept: application/vnd.github+json" "$@"; }

if [[ -z "${RUNNER_TOKEN:-}" ]]; then
  [[ -n "${SOVEREIGN_PAT:-}" ]] || { echo "need RUNNER_TOKEN or SOVEREIGN_PAT"; exit 2; }
  echo "minting registration token via API..."
  RUNNER_TOKEN=$(api -X POST "https://api.github.com/repos/$ORG/$REPO/actions/runners/registration-token" | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
fi
[[ -n "$RUNNER_TOKEN" ]] || { echo "empty registration token"; exit 2; }

ARCH=$(uname -m); case "$ARCH" in x86_64) A=x64;; aarch64|arm64) A=arm64;; *) echo "unsupported arch: $ARCH"; exit 2;; esac
VER=$(curl -s https://api.github.com/repos/actions/runner/releases/latest | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'].lstrip('v'))")
echo "runner version: $VER ($A)"

mkdir -p "$RUNNER_DIR" && cd "$RUNNER_DIR"
curl -sL -o runner.tgz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-linux-${A}-${VER#v}.tar.gz"
tar xzf runner.tgz
rm -f runner.tgz

./config.sh --url "https://github.com/$ORG/$REPO" --token "$RUNNER_TOKEN" \
  --labels "$LABELS" --unattended --replace --name "sovereign-$(hostname)-$RANDOM"

if command -v sudo >/dev/null && [[ "${SOVEREIGN_NO_SERVICE:-}" != "1" ]]; then
  sudo ./svc.sh install && sudo ./svc.sh start && echo "service installed+started"
else
  echo "SOVEREIGN_NO_SERVICE=1 (or no sudo): start manually with ./run.sh"
fi
echo "sovereign runner online — lanes with runs-on:[self-hosted,sovereign] will dequeue now"
