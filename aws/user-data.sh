#!/bin/bash
# EC2 cloud-init script for Amazon Linux 2023
# Installs Docker and Docker Compose plugin

set -euo pipefail

dnf update -y
dnf install -y docker

# Enable and start Docker
systemctl enable docker
systemctl start docker

# Install Docker Compose plugin and Buildx plugin
ARCH=$(uname -m)
mkdir -p /usr/local/lib/docker/cli-plugins

curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

case "${ARCH}" in
  x86_64)  BUILDX_ARCH="amd64" ;;
  aarch64) BUILDX_ARCH="arm64" ;;
  *)       BUILDX_ARCH="${ARCH}" ;;
esac
BUILDX_VERSION=$(curl -s https://api.github.com/repos/docker/buildx/releases/latest | grep '"tag_name"' | sed 's/.*"tag_name": "\(.*\)".*/\1/')
curl -SL "https://github.com/docker/buildx/releases/download/${BUILDX_VERSION}/buildx-${BUILDX_VERSION}.linux-${BUILDX_ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-buildx
chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx

# Add ec2-user to docker group
usermod -aG docker ec2-user

# Signal that user-data script is complete
touch /tmp/user-data-complete
