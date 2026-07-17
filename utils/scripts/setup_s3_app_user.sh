#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# setup_s3_app_user.sh — Create IAM user orbit-file-storage-app with S3 access
# =============================================================================
# Creates a dedicated IAM user + access key for ORBIT's file storage (S3
# backend) so it doesn't depend on a local AWS SSO session, which expires and
# breaks uploads. Idempotent: re-running updates the policy and rotates the
# access key.
#
# Usage:  ./setup_s3_app_user.sh
# Prereqs: Valid AWS credentials in .env (or the shell) with IAM permissions,
#          and ORBIT_S3_BUCKET already set (see env.example) or exported.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_ROOT"

if [ -f .env ]; then
    set -a; source .env; set +a
    echo "Loaded .env"
fi

export AWS_REGION="${AWS_REGION:-us-east-1}"

echo "==> Checking AWS credentials ..."
if ! aws sts get-caller-identity --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "ERROR: No valid AWS credentials."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${ORBIT_S3_BUCKET:-orbit-file-storage-${ACCOUNT_ID}}"
IAM_USER="orbit-file-storage-app"
POLICY_NAME="orbit-s3-file-storage"

if [ -z "${ORBIT_S3_BUCKET:-}" ]; then
    echo "WARNING: ORBIT_S3_BUCKET is not set; defaulting to ${BUCKET}."
    echo "         Set ORBIT_S3_BUCKET in .env to target an existing bucket."
fi

echo "  Account: $ACCOUNT_ID"
echo "  User:    $IAM_USER"
echo "  Bucket:  $BUCKET"
echo ""

if ! aws s3api head-bucket --bucket "$BUCKET" --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "ERROR: Bucket '${BUCKET}' does not exist or is not accessible."
    echo "       Create it first (see docs/aws/s3-file-storage-setup.md) — this"
    echo "       script only creates the IAM user, never the bucket."
    exit 1
fi

# ---------------------------------------------------------------------------
# 1. Create IAM user (skip if already exists)
# ---------------------------------------------------------------------------
echo "==> Step 1: Creating IAM user ${IAM_USER} ..."
if aws iam get-user --user-name "$IAM_USER" > /dev/null 2>&1; then
    echo "  User already exists, skipping creation."
else
    aws iam create-user --user-name "$IAM_USER"
    echo "  User created."
fi

# ---------------------------------------------------------------------------
# 2. Apply inline policy (idempotent — put-user-policy overwrites)
# ---------------------------------------------------------------------------
echo ""
echo "==> Step 2: Applying policy ${POLICY_NAME} ..."
aws iam put-user-policy \
    --user-name "$IAM_USER" \
    --policy-name "$POLICY_NAME" \
    --policy-document "{
        \"Version\": \"2012-10-17\",
        \"Statement\": [
            {
                \"Sid\": \"OrbitFileStorageBucketAccess\",
                \"Effect\": \"Allow\",
                \"Action\": [
                    \"s3:GetBucketLocation\",
                    \"s3:ListBucket\"
                ],
                \"Resource\": \"arn:aws:s3:::${BUCKET}\"
            },
            {
                \"Sid\": \"OrbitFileStorageObjectAccess\",
                \"Effect\": \"Allow\",
                \"Action\": [
                    \"s3:GetObject\",
                    \"s3:PutObject\",
                    \"s3:DeleteObject\"
                ],
                \"Resource\": \"arn:aws:s3:::${BUCKET}/*\"
            }
        ]
    }"
echo "  Policy applied."

# ---------------------------------------------------------------------------
# 3. Rotate access key (delete existing, create new)
# ---------------------------------------------------------------------------
echo ""
echo "==> Step 3: Rotating access key ..."
EXISTING_KEYS=$(aws iam list-access-keys \
    --user-name "$IAM_USER" \
    --query "AccessKeyMetadata[].AccessKeyId" --output text)
for key_id in $EXISTING_KEYS; do
    echo "  Deleting existing key: $key_id"
    aws iam delete-access-key --user-name "$IAM_USER" --access-key-id "$key_id"
done

KEY_JSON=$(aws iam create-access-key --user-name "$IAM_USER")
ACCESS_KEY_ID=$(echo "$KEY_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin)['AccessKey']; print(d['AccessKeyId'])")
SECRET_KEY=$(echo "$KEY_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin)['AccessKey']; print(d['SecretAccessKey'])")
echo "  Key created."

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
echo ""
echo "==> App user ready. Add these to your .env:"
echo ""
echo "  ORBIT_S3_BUCKET=${BUCKET}"
echo "  AWS_REGION=${AWS_REGION}"
echo "  ORBIT_S3_ACCESS_KEY_ID=${ACCESS_KEY_ID}"
echo "  ORBIT_S3_SECRET_ACCESS_KEY=${SECRET_KEY}"
echo ""
echo "  The secret key is shown only once — save it now."
