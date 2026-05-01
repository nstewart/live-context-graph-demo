#!/bin/bash
# Deploy Docker Compose stack to EC2
# Usage: deploy.sh <compose-command>
# Example: deploy.sh "docker compose up -d"
#          deploy.sh "docker compose --profile agent up -d"

set -euo pipefail

# Disable AWS CLI pager so commands don't block waiting for input
export AWS_PAGER=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STATE_DIR="${SCRIPT_DIR}/.state"
INSTANCE_TYPE="${INSTANCE_TYPE:-c5.4xlarge}"
COMPOSE_CMD="${1:?Usage: deploy.sh <compose-command>}"
BUNDLING_ENV="${ENABLE_DELIVERY_BUNDLING:-false}"

# Trap SIGINT to print cleanup instructions
trap 'echo ""; echo "Interrupted. To clean up AWS resources: make down-aws"; exit 130' INT

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
load_state() {
  local file="${STATE_DIR}/$1"
  if [[ -f "$file" ]]; then
    cat "$file"
  else
    echo ""
  fi
}

save_state() {
  mkdir -p "$STATE_DIR"
  echo "$2" > "${STATE_DIR}/$1"
}

log() { echo "==> $*"; }

# -------------------------------------------------------------------
# 1. Prerequisites
# -------------------------------------------------------------------
log "Checking prerequisites..."

if ! command -v aws &>/dev/null; then
  echo "Error: AWS CLI not found. Install it: https://aws.amazon.com/cli/"
  exit 1
fi

if ! aws sts get-caller-identity &>/dev/null; then
  echo "Error: AWS CLI not configured. Run 'aws configure' first."
  exit 1
fi

if ! command -v ssh &>/dev/null; then
  echo "Error: ssh not found."
  exit 1
fi

if ! command -v rsync &>/dev/null; then
  echo "Error: rsync not found."
  exit 1
fi

if [[ ! -f "${PROJECT_DIR}/.env" ]]; then
  echo "Error: .env file not found. Run 'make setup' first."
  exit 1
fi

# Get IAM username for tagging
IAM_ARN=$(aws sts get-caller-identity --query "Arn" --output text)
IAM_USER=$(echo "$IAM_ARN" | awk -F'/' '{print $NF}')

REGION=$(aws configure get region || echo "us-east-1")
save_state "region" "$REGION"

TAG_NAME="live-context-graph-${IAM_USER}"
TAG_SPECS_INSTANCE="ResourceType=instance,Tags=[{Key=Name,Value=${TAG_NAME}},{Key=Project,Value=live-context-graph},{Key=CreatedBy,Value=${IAM_USER}},{Key=ManagedBy,Value=make-up-aws}]"
TAG_SPECS_SG="ResourceType=security-group,Tags=[{Key=Name,Value=${TAG_NAME}},{Key=Project,Value=live-context-graph},{Key=CreatedBy,Value=${IAM_USER}},{Key=ManagedBy,Value=make-up-aws}]"

log "Region: $REGION | IAM User: $IAM_USER | Instance Type: $INSTANCE_TYPE"

# -------------------------------------------------------------------
# 2. Key Pair
# -------------------------------------------------------------------
KEY_NAME="live-context-graph-${IAM_USER}"
KEY_FILE="${STATE_DIR}/${KEY_NAME}.pem"
EXISTING_KEY_NAME=$(load_state "key-pair-name")

if [[ -n "$EXISTING_KEY_NAME" && -f "$(load_state 'key-file')" ]]; then
  KEY_NAME="$EXISTING_KEY_NAME"
  KEY_FILE=$(load_state "key-file")
  log "Using existing key pair: $KEY_NAME"
else
  log "Creating key pair: $KEY_NAME"
  # Delete existing key pair in AWS if it exists (stale)
  aws ec2 delete-key-pair --key-name "$KEY_NAME" 2>/dev/null || true
  mkdir -p "$STATE_DIR"
  aws ec2 create-key-pair \
    --key-name "$KEY_NAME" \
    --query "KeyMaterial" \
    --output text > "$KEY_FILE"
  chmod 600 "$KEY_FILE"
  save_state "key-pair-name" "$KEY_NAME"
  save_state "key-file" "$KEY_FILE"
fi

# -------------------------------------------------------------------
# 3. Security Group
# -------------------------------------------------------------------
SG_ID=$(load_state "security-group-id")
MY_IP=$(curl -s --max-time 5 https://checkip.amazonaws.com | tr -d '[:space:]')

if [[ -n "$SG_ID" ]]; then
  # Validate the security group still exists
  if aws ec2 describe-security-groups --group-ids "$SG_ID" &>/dev/null; then
    log "Using existing security group: $SG_ID"
    # Update ingress to current IP
    aws ec2 revoke-security-group-ingress --group-id "$SG_ID" \
      --protocol tcp --port 22 --cidr 0.0.0.0/0 2>/dev/null || true
    # Revoke any specific IP rules too
    aws ec2 revoke-security-group-ingress --group-id "$SG_ID" \
      --ip-permissions "$(aws ec2 describe-security-groups --group-ids "$SG_ID" \
        --query "SecurityGroups[0].IpPermissions" --output json 2>/dev/null)" 2>/dev/null || true
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
      --protocol tcp --port 22 --cidr "${MY_IP}/32" >/dev/null
  else
    log "Stale security group ID, creating new one..."
    SG_ID=""
  fi
fi

if [[ -z "$SG_ID" ]]; then
  # Check if a security group with this name already exists in AWS (e.g. state file was lost)
  SG_ID=$(aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=${TAG_NAME}" \
    --query "SecurityGroups[0].GroupId" --output text 2>/dev/null)
  if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
    log "Creating security group..."
    SG_ID=$(aws ec2 create-security-group \
      --group-name "$TAG_NAME" \
      --description "SSH access for live-context-graph deployment" \
      --tag-specifications "$TAG_SPECS_SG" \
      --query "GroupId" --output text)
    aws ec2 authorize-security-group-ingress --group-id "$SG_ID" \
      --protocol tcp --port 22 --cidr "${MY_IP}/32" >/dev/null
    log "Created security group: $SG_ID (SSH from $MY_IP)"
  else
    log "Recovered existing security group: $SG_ID"
  fi
  save_state "security-group-id" "$SG_ID"
fi

# -------------------------------------------------------------------
# 4. Launch EC2 (or reuse existing)
# -------------------------------------------------------------------
INSTANCE_ID=$(load_state "instance-id")

if [[ -n "$INSTANCE_ID" ]]; then
  STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].State.Name" --output text 2>/dev/null || echo "not-found")
  if [[ "$STATE" == "running" ]]; then
    log "Reusing running instance: $INSTANCE_ID"
    PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
      --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    save_state "public-ip" "$PUBLIC_IP"
  elif [[ "$STATE" == "stopped" ]]; then
    log "Starting stopped instance: $INSTANCE_ID"
    aws ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
    aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
    PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
      --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
    save_state "public-ip" "$PUBLIC_IP"
  else
    log "Instance $INSTANCE_ID is in state '$STATE', launching new one..."
    INSTANCE_ID=""
  fi
fi

if [[ -z "$INSTANCE_ID" ]]; then
  # Determine architecture from instance type family (Graviton families use aarch64)
  INSTANCE_FAMILY=$(echo "$INSTANCE_TYPE" | sed 's/[^a-zA-Z].*//')
  case "$INSTANCE_FAMILY" in
    *g*) AMI_ARCH="aarch64" ;;
    *)   AMI_ARCH="x86_64" ;;
  esac

  log "Looking up Amazon Linux 2023 AMI (${AMI_ARCH})..."
  AMI_ID=$(aws ssm get-parameters \
    --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-${AMI_ARCH} \
    --query "Parameters[0].Value" --output text)
  log "AMI: $AMI_ID"

  log "Launching EC2 instance ($INSTANCE_TYPE)..."
  INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --block-device-mappings "DeviceName=/dev/xvda,Ebs={VolumeSize=30,VolumeType=gp3}" \
    --user-data "file://${SCRIPT_DIR}/user-data.sh" \
    --tag-specifications "$TAG_SPECS_INSTANCE" \
    --query "Instances[0].InstanceId" --output text)

  save_state "instance-id" "$INSTANCE_ID"
  log "Launched instance: $INSTANCE_ID"

  log "Waiting for instance to be running..."
  aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

  PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
  save_state "public-ip" "$PUBLIC_IP"
  log "Instance IP: $PUBLIC_IP"
fi

# -------------------------------------------------------------------
# 5. Wait for SSH + Docker
# -------------------------------------------------------------------
SSH_OPTS="-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -i $KEY_FILE"

log "Waiting for SSH access..."
for i in $(seq 1 30); do
  if ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "true" 2>/dev/null; then
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "Error: SSH connection timed out after 30 attempts"
    exit 1
  fi
  sleep 5
done

log "Waiting for cloud-init to complete..."
for i in $(seq 1 60); do
  if ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "test -f /tmp/user-data-complete" 2>/dev/null; then
    break
  fi
  if [[ $i -eq 60 ]]; then
    echo "Error: cloud-init did not complete within timeout"
    exit 1
  fi
  sleep 5
done

log "Verifying Docker..."
ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "docker info" >/dev/null 2>&1 || {
  echo "Error: Docker is not available on the instance"
  exit 1
}

# -------------------------------------------------------------------
# 6. Rsync project
# -------------------------------------------------------------------
log "Syncing project files to EC2..."
RSYNC_OUTPUT=$(rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude '__pycache__' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'aws/.state' \
  --exclude '.pytest_cache' \
  --exclude '.ruff_cache' \
  --exclude 'dist' \
  --exclude '.vite' \
  -e "ssh $SSH_OPTS" \
  "${PROJECT_DIR}/" \
  ec2-user@"$PUBLIC_IP":~/app/ 2>&1) || {
    echo "Error: rsync failed:"
    echo "$RSYNC_OUTPUT"
    exit 1
  }
log "Sync complete."

# -------------------------------------------------------------------
# 7. Deploy compose
# -------------------------------------------------------------------
log "Deploying Docker Compose stack..."

# Build the remote command
REMOTE_CMD="cd ~/app"
REMOTE_CMD="${REMOTE_CMD} && docker network create freshmart-network 2>/dev/null || true"

# Set bundling env var if needed
if [[ "$BUNDLING_ENV" == "true" ]]; then
  REMOTE_CMD="${REMOTE_CMD} && export ENABLE_DELIVERY_BUNDLING=true"
fi

# Build web and zero-permissions first
if [[ "$BUNDLING_ENV" == "true" ]]; then
  REMOTE_CMD="${REMOTE_CMD} && ENABLE_DELIVERY_BUNDLING=true docker compose build web zero-permissions"
else
  REMOTE_CMD="${REMOTE_CMD} && docker compose build web zero-permissions"
fi

# Force recreate materialize-init
REMOTE_CMD="${REMOTE_CMD} && docker compose rm -f materialize-init 2>/dev/null || true"

# Wipe Zero's persisted state so it boots clean against a freshly-initialized
# Materialize. Materialize has no volume (see compose) so its state resets every
# deploy; zero-cache's replica.db is now ephemeral (no named volume) but the
# zero_change/zero_cvr metadata DBs live in app_postgres_data and must be reset
# explicitly, or zero-cache will crash-loop on stale watermarks.
REMOTE_CMD="${REMOTE_CMD} && docker compose rm -fsv zero-cache materialize-zero zero-permissions 2>/dev/null || true"
REMOTE_CMD="${REMOTE_CMD} && docker volume rm app_zero_data 2>/dev/null || true"
REMOTE_CMD="${REMOTE_CMD} && docker compose up -d --wait db"
REMOTE_CMD="${REMOTE_CMD} && docker compose exec -T db psql -U postgres -c \"DROP DATABASE IF EXISTS zero_change WITH (FORCE);\""
REMOTE_CMD="${REMOTE_CMD} && docker compose exec -T db psql -U postgres -c \"DROP DATABASE IF EXISTS zero_cvr WITH (FORCE);\""
REMOTE_CMD="${REMOTE_CMD} && docker compose exec -T db psql -U postgres -c \"CREATE DATABASE zero_change;\""
REMOTE_CMD="${REMOTE_CMD} && docker compose exec -T db psql -U postgres -c \"CREATE DATABASE zero_cvr;\""

# Run the compose command
REMOTE_CMD="${REMOTE_CMD} && ${COMPOSE_CMD}"

ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "$REMOTE_CMD" || {
    echo "Error: Docker Compose deployment failed"
    exit 1
  }
log "Docker Compose stack deployed."

# Stabilize the Zero stack against Materialize. Two failure modes can drive
# zero-cache into an AutoResetSignal loop that does not self-recover:
#   1. zero-cache subscribes before materialize-zero has finished hydrating
#      its collections — gated by mz_internal.mz_hydration_statuses below.
#   2. materialize-zero asks Materialize for a timestamp mz has compacted past
#      (OutOfBoundsTimestampError) — typically a transient timestamp-oracle
#      skew when materialize-zero connects shortly after a fresh boot.
# We handle (1) with the hydration gate and (2) with a one-shot self-heal:
# if zero-cache is restart-looping, we drop the metadata DBs, recreate the
# whole Zero stack, wait for hydration again, and re-check stability. Two
# attempts is enough — if it still loops, the deploy fails loud.
log "Stabilizing Zero stack..."
ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" bash <<'EOF' || { echo "Error: zero-cache could not be stabilized"; exit 1; }
set -e
cd ~/app

COLLECTIONS="orders_flat_mv,courier_schedule_mv,customers_mv,orders_search_source_mv,products_mv,store_inventory_mv,stores_mv,orders_with_lines_mv,inventory_items_with_dynamic_pricing_mv,pricing_yield_mv,inventory_risk_mv,store_capacity_health_mv,delivery_bundles_mv,compatible_pairs_mv"
EXPECTED=$(echo "$COLLECTIONS" | tr ',' '\n' | wc -l | tr -d ' ')
QUOTED=$(echo "$COLLECTIONS" | sed "s/,/','/g; s/^/'/; s/$/'/")
HYDRATION_SQL="SELECT count(*) FROM mz_internal.mz_hydration_statuses hs JOIN mz_catalog.mz_materialized_views mv ON mv.id = hs.object_id WHERE mv.name IN ($QUOTED) AND hs.hydrated;"

wait_for_hydration() {
  echo "Waiting for $EXPECTED Materialize views to hydrate..."
  local i hydrated=0
  for i in $(seq 1 60); do
    sleep 5
    hydrated=$(docker compose exec -T mz psql -h localhost -p 6875 -U materialize -d materialize -tAc "$HYDRATION_SQL" 2>/dev/null | tr -d ' \r\n' || echo 0)
    if [ "$hydrated" = "$EXPECTED" ]; then
      echo "  All $EXPECTED views hydrated after $((i*5))s"
      return 0
    fi
  done
  echo "  ERROR: only $hydrated/$EXPECTED views hydrated after 300s"
  docker compose exec -T mz psql -h localhost -p 6875 -U materialize -d materialize -c "SELECT mv.name, hs.hydrated FROM mz_internal.mz_hydration_statuses hs RIGHT JOIN mz_catalog.mz_materialized_views mv ON mv.id = hs.object_id WHERE mv.name IN ($QUOTED) ORDER BY mv.name;" || true
  return 1
}

reset_zero_stack() {
  echo "Resetting Zero stack (containers + metadata DBs)..."
  docker compose rm -fsv zero-cache materialize-zero zero-permissions 2>/dev/null || true
  docker compose exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS zero_change WITH (FORCE);" >/dev/null
  docker compose exec -T db psql -U postgres -c "DROP DATABASE IF EXISTS zero_cvr WITH (FORCE);" >/dev/null
  docker compose exec -T db psql -U postgres -c "CREATE DATABASE zero_change;" >/dev/null
  docker compose exec -T db psql -U postgres -c "CREATE DATABASE zero_cvr;" >/dev/null
  docker compose up -d materialize-zero zero-cache zero-permissions
}

clear_reset_flag() {
  # zero-cache's auto-reset path sets resetRequired=true in zero_change on
  # every reset-required signal it receives, and reads it on every restart
  # WITHOUT clearing it. Once set, zero-cache enters an infinite
  # AutoResetSignal loop that doesn't self-recover even after the upstream
  # cause is fixed. Clear it before each (re)start.
  docker compose exec -T db psql -U postgres -d zero_change -c \
    'UPDATE "zero_0/cdc"."replicationConfig" SET "resetRequired" = false;' \
    >/dev/null 2>&1 || true
}

recreate_zero_cache() {
  echo "Recreating zero-cache against hydrated upstream..."
  docker compose rm -fsv zero-cache >/dev/null
  clear_reset_flag
  docker compose up -d zero-cache >/dev/null
}

verify_stability() {
  # Watch for restarts over 60s. A delta > 1 indicates an AutoResetSignal loop
  # (the WebSocket failure mode that appears in the browser as
  # "WebSocket connection closed abruptly" at ws://localhost:4848).
  echo "Verifying zero-cache stability..."
  local before now delta i
  sleep 5  # let the new container settle
  before=$(docker inspect -f '{{.RestartCount}}' zero-cache 2>/dev/null || echo 0)
  for i in $(seq 1 12); do
    sleep 5
    now=$(docker inspect -f '{{.RestartCount}}' zero-cache 2>/dev/null || echo 0)
    delta=$((now - before))
    if [ "$delta" -gt 1 ]; then
      echo "  zero-cache restarted $delta times in $((i*5))s — unstable"
      return 1
    fi
  done
  echo "  zero-cache stable (delta=$delta after 60s)"
  return 0
}

# Attempt 1: wait for hydration, recreate zero-cache, check stability.
wait_for_hydration || exit 1
recreate_zero_cache
verify_stability && exit 0

# Attempt 2: full Zero-stack reset (covers OutOfBoundsTimestampError and other
# transient handshake failures that don't self-recover within 60s).
echo "Stability check failed — performing full Zero-stack reset and retrying"
reset_zero_stack
wait_for_hydration || exit 1
verify_stability && exit 0

echo "ERROR: zero-cache could not stabilize after 2 attempts"
docker compose logs --tail=80 zero-cache
exit 1
EOF

log "Waiting for databases to be ready..."
sleep 10

# Run migrations
log "Running migrations..."
ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "cd ~/app && ./db/scripts/run_migrations.sh"

# Seed data
log "Loading seed data..."
ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "cd ~/app && docker compose --profile seed build db-seed && docker compose --profile seed run --rm db-seed"

# Init checkpointer if agent profile
if echo "$COMPOSE_CMD" | grep -q "agent"; then
  log "Waiting for agent services to be ready..."
  sleep 5
  log "Initializing agent checkpointer..."
  ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "cd ~/app && docker compose exec agents env PYTHONPATH=/app python -m src.init_checkpointer"
fi

# -------------------------------------------------------------------
# 8. SSH Tunnel
# -------------------------------------------------------------------
log "Setting up SSH tunnel..."
"${SCRIPT_DIR}/ssh-tunnel.sh" stop 2>/dev/null || true
"${SCRIPT_DIR}/ssh-tunnel.sh" start

log ""
log "Deployment complete!"
log "  Instance:  $INSTANCE_ID ($PUBLIC_IP)"
log "  Type:      $INSTANCE_TYPE"
log ""
log "Services available at:"
log "  Web UI:     http://localhost:5173"
log "  API:        http://localhost:8080"
log "  PostgreSQL: localhost:5432"
log "  Materialize: localhost:6875"
log "  OpenSearch: http://localhost:9200"
log ""
log "Useful commands:"
log "  make aws-logs    - Tail remote logs"
log "  make aws-ssh     - SSH into the instance"
log "  make aws-tunnel  - Re-establish SSH tunnel"
log "  make aws-status  - Check status"
log "  make down-aws    - Tear down everything"
