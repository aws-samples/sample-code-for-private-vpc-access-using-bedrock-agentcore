#!/bin/bash
set -e

# Profile support: pass --profile <name> or set AWS_PROFILE env var
PROFILE_ARG=""
if [ -n "$AWS_PROFILE" ]; then
    PROFILE_ARG="--profile $AWS_PROFILE"
elif [ "$1" = "--profile" ] && [ -n "$2" ]; then
    export AWS_PROFILE="$2"
    PROFILE_ARG="--profile $2"
    shift 2
fi

echo "Deploying agent ..."

REGION=$(aws $PROFILE_ARG configure get region || echo "us-east-1")

agentcore configure \
    --entrypoint agent.py \
    --requirements-file requirements.txt \
    --name campaign_agent \
    --region $REGION \
    --disable-memory \
    --non-interactive

agentcore deploy

# Wait for runtime to be ready
echo ""
echo "=== Waiting for Runtime to be Ready ==="
MAX_WAIT=120
WAIT_INTERVAL=10
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
  RUNTIME_INFO=$(agentcore status --verbose 2>/dev/null)
  RUNTIME_STATUS=$(echo "$RUNTIME_INFO" | grep -o '"status": "[^"]*"' | head -1 | cut -d'"' -f4)

  if [ "$RUNTIME_STATUS" = "READY" ]; then
    echo "✅ Runtime is READY"
    break
  fi

  echo "  Runtime status: $RUNTIME_STATUS (${ELAPSED}s elapsed)"
  sleep $WAIT_INTERVAL
  ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ "$RUNTIME_STATUS" != "READY" ]; then
  echo "⚠️  Runtime not READY after ${MAX_WAIT}s. Current status: $RUNTIME_STATUS"
fi

RUNTIME_INFO=$(agentcore status --verbose 2>/dev/null)
RUNTIME_ARN=$(echo "$RUNTIME_INFO" | tr -d '\n' | grep -o '"agent_arn": "[^"]*"' | cut -d'"' -f4)
aws $PROFILE_ARG ssm put-parameter --name /campaign/agent-runtime-arn --value "$RUNTIME_ARN" --type String --overwrite
echo "✅ Runtime ARN saved: $RUNTIME_ARN"

echo "=== Step 7: Add IAM Permissions ==="
RUNTIME_INFO=$(agentcore status --verbose 2>/dev/null)
ROLE_ARN=$(echo "$RUNTIME_INFO" | tr -d '\n' | grep -o '"execution_role": "[^"]*"' | cut -d'"' -f4)
ROLE_NAME=$(echo "$ROLE_ARN" | awk -F'/' '{print $NF}')
ACCOUNT_ID=$(aws $PROFILE_ARG sts get-caller-identity --query Account --output text)
echo "Role Name: $ROLE_NAME"


# Create inline policy for SSM and Secrets Manager access
aws $PROFILE_ARG iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name AgentServerSSMAccess \
    --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["ssm:GetParameter","ssm:GetParameters"],"Resource":"arn:aws:ssm:'"$REGION"':'"$ACCOUNT_ID"':parameter/campaign/*"},{"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":"arn:aws:secretsmanager:'"$REGION"':'"$ACCOUNT_ID"':secret:CampaignRdsStack*"}]}'

echo "✅ IAM permissions added!"

echo "✓ Deployment complete!"
