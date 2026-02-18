# AWS Deployment

Deploy the FreshMart Digital Twin stack to an EC2 instance with a single command. All AWS resources are managed automatically and torn down cleanly when you're done.

## Prerequisites

- **AWS CLI** — [Install guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **AWS credentials** — Run `aws configure` or set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
- **AWS region** — Set via `aws configure set region <region>` or the `AWS_DEFAULT_REGION` env var
- **ssh** and **rsync** — Pre-installed on macOS; on Linux install via your package manager
- **`.env` file** — Must exist in the project root (copy from `.env.example` if needed)

### IAM Permissions

Ask your AWS admin to add your IAM user to the **`live-context-graph-deployers`** group, which has the **`live-context-graph-ec2-deploy`** policy attached. This grants:

| Service | Permissions |
|---------|------------|
| EC2 | `RunInstances`, `TerminateInstances`, `StartInstances`, `DescribeInstances`, `CreateKeyPair`, `DeleteKeyPair`, `DescribeKeyPairs`, `CreateSecurityGroup`, `DeleteSecurityGroup`, `DescribeSecurityGroups`, `AuthorizeSecurityGroupIngress`, `RevokeSecurityGroupIngress`, `CreateTags` |
| SSM | `GetParameters` (for AMI lookup) |
| STS | `GetCallerIdentity` |

## Quick Start

```bash
# 1. Verify your setup
make aws-debug

# 2. Deploy (pick one)
make up-aws                  # without agent
make up-agent-aws            # with agent
make up-agent-bundling-aws   # with agent + delivery bundling

# 3. Open the app
open http://localhost:5173

# 4. Tear down when done
make down-aws
```

## Commands

| Command | Description |
|---------|-------------|
| `make aws-debug` | Preflight check — validates AWS CLI, credentials, region, IAM permissions, and local tools |
| `make up-aws` | Deploy to EC2 (without agent) |
| `make up-agent-aws` | Deploy to EC2 (with agent) |
| `make up-agent-bundling-aws` | Deploy to EC2 (with agent + delivery bundling) |
| `make down-aws` | Terminate the EC2 instance and delete all AWS resources |
| `make aws-tunnel` | Re-establish the SSH tunnel (if disconnected) |
| `make aws-ssh` | SSH into the EC2 instance |
| `make aws-logs` | Tail Docker Compose logs on the remote instance |
| `make aws-status` | Check instance and tunnel status |

## How It Works

### Deployment (`make up-aws`)

1. Creates (or reuses) an SSH key pair and security group
2. Launches an **m5.2xlarge** EC2 instance running Amazon Linux 2023
3. Installs Docker and Docker Compose via cloud-init
4. Syncs the project to `~/app` on the instance using rsync
5. Builds images and starts Docker Compose services
6. Runs database migrations and loads seed data
7. Opens an SSH tunnel so services are accessible on localhost

### SSH Tunnel

The tunnel forwards all service ports to your local machine:

| Local Port | Service |
|-----------|---------|
| 5173 | Web UI |
| 8080 | API |
| 8081 | Agent |
| 5432 | PostgreSQL |
| 6874 | Materialize Console |
| 6875 | Materialize SQL |
| 9200 | OpenSearch |
| 5601 | OpenSearch Dashboards |

If the tunnel drops, re-establish it with `make aws-tunnel`.

### Teardown (`make down-aws`)

Removes everything created during deployment:

- Terminates the EC2 instance
- Deletes the security group and key pair
- Removes local state files and the `.pem` key

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `INSTANCE_TYPE` | `m5.2xlarge` | EC2 instance type |
| `ENABLE_DELIVERY_BUNDLING` | *(unset)* | Set to `true` for delivery bundling (CPU intensive) |

## Troubleshooting

### Run the preflight check first

```bash
make aws-debug
```

This validates your AWS CLI installation, credentials, region, IAM permissions, and local tools. Fix any reported issues before deploying.

### Common issues

**"No credentials" or "InvalidClientTokenId"**
Run `aws configure` and enter your access key and secret key, or export `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.

**"No region configured"**
Run `aws configure set region us-east-1` (or your preferred region), or export `AWS_DEFAULT_REGION`.

**"UnauthorizedOperation" on EC2 calls**
Your IAM user is missing EC2 permissions. Ask your AWS admin to add you to the `live-context-graph-deployers` IAM group.

**SSH tunnel disconnects**
Run `make aws-tunnel` to re-establish. The tunnel uses keep-alive settings but may drop on network changes.

**Deployment hangs at "Waiting for SSH access"**
The security group may not allow SSH from your current IP. If your IP changed since the last deploy, tear down (`make down-aws`) and redeploy.

**Port conflict on localhost**
Another process is using one of the forwarded ports. Stop the conflicting process or adjust your local services before running `make aws-tunnel`.

## State Files

Deployment state is stored in `aws/.state/` (git-ignored). Do not edit these files manually. If state becomes corrupted, run `make down-aws` to clean up, then redeploy.
