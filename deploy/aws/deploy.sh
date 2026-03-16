#!/usr/bin/env bash
#
# Deploy Hivemind Cloud to EC2 with Amazon RDS PostgreSQL.
# Requires DATABASE_URL in .env.aws pointing to your RDS instance.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.ec2.yml"
ENV_FILE="$SCRIPT_DIR/.env.aws"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  echo "Copy deploy/aws/.env.example to deploy/aws/.env.aws and set DATABASE_URL (RDS)."
  exit 1
fi

HIVEMIND_ENV_FILE="$ENV_FILE" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --build
HIVEMIND_ENV_FILE="$ENV_FILE" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo ""
echo "Hivemind Cloud is deploying."
echo "Follow logs with:"
echo "  HIVEMIND_ENV_FILE=\"$ENV_FILE\" docker compose --env-file \"$ENV_FILE\" -f \"$COMPOSE_FILE\" logs -f app"
