#!/bin/bash
# Tear down EC2 instance and clean up all AWS resources
# Usage: teardown.sh

set -euo pipefail

# Disable AWS CLI pager so commands don't block waiting for input
export AWS_PAGER=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${SCRIPT_DIR}/.state"

log() { echo "==> $*"; }

load_state() {
  local file="${STATE_DIR}/$1"
  if [[ -f "$file" ]]; then
    cat "$file"
  else
    echo ""
  fi
}

if [[ ! -d "$STATE_DIR" ]]; then
  echo "No state directory found. Nothing to tear down."
  exit 0
fi

# 1. Stop SSH tunnel
log "Stopping SSH tunnel..."
"${SCRIPT_DIR}/ssh-tunnel.sh" stop 2>/dev/null || true

# 2. Terminate EC2 instance
INSTANCE_ID=$(load_state "instance-id")
if [[ -n "$INSTANCE_ID" ]]; then
  STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query "Reservations[0].Instances[0].State.Name" --output text 2>/dev/null || echo "not-found")
  if [[ "$STATE" != "terminated" && "$STATE" != "not-found" ]]; then
    log "Terminating instance: $INSTANCE_ID"
    aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null
    log "Waiting for instance to terminate..."
    aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"
    log "Instance terminated"
  else
    log "Instance already terminated or not found"
  fi
fi

# 3. Delete security group (with retry for ENI detach delay)
SG_ID=$(load_state "security-group-id")
if [[ -n "$SG_ID" ]]; then
  log "Deleting security group: $SG_ID"
  for i in $(seq 1 12); do
    if aws ec2 delete-security-group --group-id "$SG_ID" 2>/dev/null; then
      log "Security group deleted"
      break
    fi
    if [[ $i -eq 12 ]]; then
      echo "Warning: Could not delete security group $SG_ID after 12 attempts"
      echo "         It may still have dependent ENIs. Delete manually in AWS Console."
    else
      sleep 10
    fi
  done
fi

# 4. Delete key pair
KEY_NAME=$(load_state "key-pair-name")
KEY_FILE=$(load_state "key-file")
if [[ -n "$KEY_NAME" ]]; then
  log "Deleting key pair: $KEY_NAME"
  aws ec2 delete-key-pair --key-name "$KEY_NAME" 2>/dev/null || true
fi
if [[ -n "$KEY_FILE" && -f "$KEY_FILE" ]]; then
  rm -f "$KEY_FILE"
fi

# 5. Remove state directory
log "Removing state directory..."
rm -rf "$STATE_DIR"

log "Teardown complete. All AWS resources cleaned up."
