#!/bin/bash
# SSH tunnel management for EC2-deployed Docker Compose stack
# Usage: ssh-tunnel.sh start|stop|status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${SCRIPT_DIR}/.state"

usage() {
  echo "Usage: $0 {start|stop|status}"
  exit 1
}

load_state() {
  local file="${STATE_DIR}/$1"
  if [[ -f "$file" ]]; then
    cat "$file"
  else
    echo ""
  fi
}

start_tunnel() {
  local ip key_file pid_file
  ip=$(load_state "public-ip")
  key_file=$(load_state "key-file")
  pid_file="${STATE_DIR}/tunnel-pid"

  if [[ -z "$ip" || -z "$key_file" ]]; then
    echo "Error: No instance state found. Run deploy.sh first."
    exit 1
  fi

  # Check if tunnel is already running
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      echo "SSH tunnel already running (PID $pid)"
      return 0
    fi
    rm -f "$pid_file"
  fi

  echo "Starting SSH tunnel to $ip..."

  ssh -N -f \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ServerAliveInterval=30 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o LogLevel=ERROR \
    -i "$key_file" \
    -L 5432:localhost:5432 \
    -L 6874:localhost:6874 \
    -L 6875:localhost:6875 \
    -L 9200:localhost:9200 \
    -L 5601:localhost:5601 \
    -L 8080:localhost:8080 \
    -L 8081:localhost:8081 \
    -L 8082:localhost:8082 \
    -L 8083:localhost:8083 \
    -L 8084:localhost:8084 \
    -L 5173:localhost:5173 \
    -L 4848:localhost:4848 \
    ec2-user@"$ip"

  # Find the SSH process we just started
  local tunnel_pid
  tunnel_pid=$(pgrep -f "ssh.*-L 5432:localhost:5432.*${ip}" | head -1)

  if [[ -n "$tunnel_pid" ]]; then
    echo "$tunnel_pid" > "$pid_file"
    echo "SSH tunnel established (PID $tunnel_pid)"
    echo ""
    echo "Port forwards:"
    echo "  PostgreSQL:            localhost:5432"
    echo "  Materialize Console:   localhost:6874"
    echo "  Materialize SQL:       localhost:6875"
    echo "  OpenSearch:            localhost:9200"
    echo "  OpenSearch Dashboards: localhost:5601"
    echo "  API:                   localhost:8080"
    echo "  Agent:                 localhost:8081"
    echo "  Materialize Zero:      localhost:8082"
    echo "  Search Sync:           localhost:8083"
    echo "  Load Generator:        localhost:8084"
    echo "  Web UI:                localhost:5173"
    echo "  Zero Cache:            localhost:4848"
  else
    echo "Error: Failed to establish SSH tunnel"
    exit 1
  fi
}

stop_tunnel() {
  local pid_file="${STATE_DIR}/tunnel-pid"

  if [[ ! -f "$pid_file" ]]; then
    echo "No tunnel PID file found"
    return 0
  fi

  local pid
  pid=$(cat "$pid_file")

  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "SSH tunnel stopped (PID $pid)"
  else
    echo "SSH tunnel process not running (stale PID $pid)"
  fi

  rm -f "$pid_file"
}

tunnel_status() {
  local pid_file="${STATE_DIR}/tunnel-pid"
  local ip
  ip=$(load_state "public-ip")

  if [[ ! -f "$pid_file" ]]; then
    echo "SSH tunnel: not running (no PID file)"
    return 1
  fi

  local pid
  pid=$(cat "$pid_file")

  if kill -0 "$pid" 2>/dev/null; then
    echo "SSH tunnel: running (PID $pid, target $ip)"
    return 0
  else
    echo "SSH tunnel: not running (stale PID $pid)"
    rm -f "$pid_file"
    return 1
  fi
}

[[ $# -lt 1 ]] && usage

case "$1" in
  start)  start_tunnel ;;
  stop)   stop_tunnel ;;
  status) tunnel_status ;;
  *)      usage ;;
esac
