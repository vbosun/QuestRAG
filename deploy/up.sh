#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
env_file="${QUESTRAG_ENV_FILE:-.env.compose}"
if [[ ! -f "$env_file" ]]; then
  printf 'Create %s from deploy/compose.env.example and fill the configuration first.\n' "$env_file" >&2
  exit 1
fi
export QUESTRAG_ENV_FILE="$env_file"
docker compose --env-file "$env_file" config -q
docker compose --env-file "$env_file" build backend browser-worker web
docker compose --env-file "$env_file" up -d --wait --wait-timeout 180
docker compose --env-file "$env_file" ps
