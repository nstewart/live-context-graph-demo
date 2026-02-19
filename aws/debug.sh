#!/usr/bin/env bash
set -euo pipefail

# Disable AWS CLI pager so commands don't block waiting for input
export AWS_PAGER=""

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
NC='\033[0m' # No Color

pass() { echo -e "  ${GREEN}✔${NC} $1"; }
fail() { echo -e "  ${RED}✘${NC} $1"; }

echo ""
echo -e "${BOLD}AWS Preflight Check${NC}"
echo "==================="
echo ""

# 1. AWS CLI installed
if ! command -v aws &>/dev/null; then
    fail "AWS CLI is not installed"
    echo "    Install it: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi
pass "AWS CLI installed ($(aws --version 2>&1 | head -1))"

# 2. AWS CLI configured (sts get-caller-identity)
CALLER_IDENTITY=$(aws sts get-caller-identity --output json 2>&1) || {
    fail "AWS CLI is not configured or credentials are invalid"
    echo "    Run: aws configure"
    echo "    Or set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables"
    exit 1
}
ACCOUNT_ID=$(echo "$CALLER_IDENTITY" | grep '"Account"' | sed 's/.*: "\(.*\)".*/\1/')
USER_ARN=$(echo "$CALLER_IDENTITY" | grep '"Arn"' | sed 's/.*: "\(.*\)".*/\1/')
pass "AWS credentials valid (account: ${ACCOUNT_ID})"

# 3. Region resolved
REGION=$(aws configure get region 2>/dev/null || echo "")
if [ -z "$REGION" ]; then
    REGION="${AWS_DEFAULT_REGION:-}"
fi
if [ -z "$REGION" ]; then
    fail "No AWS region configured"
    echo "    Run: aws configure set region us-east-1"
    echo "    Or set AWS_DEFAULT_REGION environment variable"
    exit 1
fi
pass "Region: ${REGION}"

# 4. EC2 describe-instances permission
EC2_RESULT=$(aws ec2 describe-instances --dry-run 2>&1) || true
if echo "$EC2_RESULT" | grep -q "DryRunOperation"; then
    pass "EC2 describe-instances permission"
elif echo "$EC2_RESULT" | grep -q "UnauthorizedOperation"; then
    fail "Missing EC2 describe-instances permission"
    echo "    Your IAM user/role needs the ec2:DescribeInstances permission"
    exit 1
else
    fail "EC2 describe-instances check failed: ${EC2_RESULT}"
    exit 1
fi

# 5. EC2 describe-key-pairs permission
KP_RESULT=$(aws ec2 describe-key-pairs --dry-run 2>&1) || true
if echo "$KP_RESULT" | grep -q "DryRunOperation"; then
    pass "EC2 describe-key-pairs permission"
elif echo "$KP_RESULT" | grep -q "UnauthorizedOperation"; then
    fail "Missing EC2 describe-key-pairs permission"
    echo "    Your IAM user/role needs the ec2:DescribeKeyPairs permission"
    exit 1
else
    fail "EC2 describe-key-pairs check failed: ${KP_RESULT}"
    exit 1
fi

# 6. EC2 describe-security-groups permission
SG_RESULT=$(aws ec2 describe-security-groups --dry-run 2>&1) || true
if echo "$SG_RESULT" | grep -q "DryRunOperation"; then
    pass "EC2 describe-security-groups permission"
elif echo "$SG_RESULT" | grep -q "UnauthorizedOperation"; then
    fail "Missing EC2 describe-security-groups permission"
    echo "    Your IAM user/role needs the ec2:DescribeSecurityGroups permission"
    exit 1
else
    fail "EC2 describe-security-groups check failed: ${SG_RESULT}"
    exit 1
fi

# 7. SSM read access (AMI lookup)
INSTANCE_FAMILY=$(echo "${INSTANCE_TYPE:-m5}" | sed 's/[^a-zA-Z].*//')
case "$INSTANCE_FAMILY" in
    *g*) AMI_ARCH="aarch64" ;;
    *)   AMI_ARCH="x86_64" ;;
esac
SSM_RESULT=$(aws ssm get-parameters \
    --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-${AMI_ARCH} \
    --output json 2>&1) || {
    fail "SSM parameter read failed (needed for AMI lookup)"
    echo "    Your IAM user/role needs the ssm:GetParameters permission"
    exit 1
}
if echo "$SSM_RESULT" | grep -q '"InvalidParameters": \[\]'; then
    pass "SSM read access (AMI lookup)"
elif echo "$SSM_RESULT" | grep -q '"InvalidParameters"'; then
    fail "SSM parameter not found (AMI lookup may fail)"
    echo "    The AL2023 AMI parameter was not found in region ${REGION}"
    exit 1
else
    pass "SSM read access (AMI lookup)"
fi

# 8. Local tools
if ! command -v ssh &>/dev/null; then
    fail "ssh is not installed"
    echo "    Install OpenSSH client for your platform"
    exit 1
fi
pass "ssh available"

if ! command -v rsync &>/dev/null; then
    fail "rsync is not installed"
    echo "    Install rsync: brew install rsync (macOS) or apt install rsync (Linux)"
    exit 1
fi
pass "rsync available"

# Summary
echo ""
echo -e "${GREEN}${BOLD}All checks passed!${NC}"
echo ""
echo "  Region:  ${REGION}"
echo "  Account: ${ACCOUNT_ID}"
echo "  IAM ARN: ${USER_ARN}"
echo ""
echo "You are ready to run 'make up-aws'."
echo ""
