#!/bin/bash
# Deploy MCP Server to Amazon Bedrock AgentCore Runtime with VPC and Authentication

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

# Get VPC configuration from Parameter Store
echo "=== Step 1: Get VPC Configuration ==="
REGION=$(aws $PROFILE_ARG configure get region)
SUBNET_IDS=$(aws $PROFILE_ARG ssm get-parameter --name /campaign/private-subnet-ids --query 'Parameter.Value' --output text)
SECURITY_GROUP_ID=$(aws $PROFILE_ARG ssm get-parameter --name /campaign/mcp-sg-id --query 'Parameter.Value' --output text)

echo "Region: $REGION"
echo "Subnet IDs: $SUBNET_IDS"
echo "Security Group ID: $SECURITY_GROUP_ID"

# Get Cognito configuration
echo ""
echo "=== Step 2: Get Cognito Configuration ==="
DISCOVERY_URL=$(aws $PROFILE_ARG ssm get-parameter --name /campaign/mcp-runtime-discovery-url --query 'Parameter.Value' --output text)
CLIENT_ID=$(aws $PROFILE_ARG ssm get-parameter --name /campaign/mcp-runtime-client-id --query 'Parameter.Value' --output text)

echo "Discovery URL: $DISCOVERY_URL"
echo "Client ID: $CLIENT_ID"

# Configure agent with VPC settings and authentication
echo ""
echo "=== Step 3: Configure AgentCore Runtime ==="
agentcore configure \
    --entrypoint server.py \
    --requirements-file requirements.txt \
    --name campaign_mcp_server \
    --region $REGION \
    --vpc \
    --subnets $SUBNET_IDS \
    --security-groups $SECURITY_GROUP_ID \
    --protocol MCP \
    --authorizer-config "{\"customJWTAuthorizer\":{\"allowedClients\":[\"$CLIENT_ID\"],\"discoveryUrl\":\"$DISCOVERY_URL\"}}" \
    --disable-memory \
    --non-interactive

# Deploy to AgentCore Runtime
echo ""
echo "=== Step 4: Deploy to AgentCore Runtime ==="
agentcore deploy

# Wait for runtime to be ready and get runtime info
echo ""
echo "=== Step 5: Wait for Runtime to be Ready ==="
MAX_WAIT=30  # Maximum wait time in seconds
WAIT_INTERVAL=10
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
  echo "Checking runtime status... (${ELAPSED}s elapsed)"
  
  RUNTIME_INFO=$(agentcore status --verbose 2>/dev/null)
  RUNTIME_STATUS=$(echo "$RUNTIME_INFO" | grep -o '"status": "[^"]*"' | head -1 | cut -d'"' -f4)
  
  if [ "$RUNTIME_STATUS" = "READY" ]; then
    echo "✅ Runtime is READY"
    break
  fi
  
  echo "Runtime status: $RUNTIME_STATUS (waiting...)"
  sleep $WAIT_INTERVAL
  ELAPSED=$((ELAPSED + WAIT_INTERVAL))
done

if [ "$RUNTIME_STATUS" != "READY" ]; then
  echo "⚠️  Warning: Runtime not READY after ${MAX_WAIT}s. Current status: $RUNTIME_STATUS"
  echo "You may need to check runtime status manually with: agentcore status --verbose"
fi

# Get runtime info and save to Parameter Store
echo ""
echo "=== Step 6: Save Runtime Config to Parameter Store ==="
RUNTIME_ID=$(echo "$RUNTIME_INFO" | grep -o '"agent_id": "[^"]*"' | cut -d'"' -f4)
RUNTIME_ARN=$(echo "$RUNTIME_INFO" | tr -d '\n' | grep -o '"agent_arn": "[^"]*"' | cut -d'"' -f4)

aws $PROFILE_ARG ssm put-parameter --name /campaign/mcp-runtime-id --value "$RUNTIME_ID" --type String --overwrite

# Only save ARN if it's not empty
if [ -n "$RUNTIME_ARN" ]; then
  aws $PROFILE_ARG ssm put-parameter --name /campaign/mcp-runtime-arn --value "$RUNTIME_ARN" --type String --overwrite
  echo "✅ Runtime ARN saved: $RUNTIME_ARN"
else
  echo "⚠️  Warning: Runtime ARN not available. You can retrieve it later with: agentcore status --verbose"
fi

echo ""
echo "✅ Runtime deployed successfully!"
echo "Runtime ID: $RUNTIME_ID"
echo "Runtime ARN: $RUNTIME_ARN"

# Add IAM permissions for SSM and Secrets Manager
echo ""
echo "=== Step 7: Add IAM Permissions ==="
RUNTIME_INFO=$(agentcore status --verbose 2>/dev/null)
ROLE_ARN=$(echo "$RUNTIME_INFO" | tr -d '\n' | grep -o '"execution_role": "[^"]*"' | cut -d'"' -f4)
ROLE_NAME=$(echo "$ROLE_ARN" | awk -F'/' '{print $NF}')
ACCOUNT_ID=$(aws $PROFILE_ARG sts get-caller-identity --query Account --output text)
echo "Role Name: $ROLE_NAME"


# Create inline policy for SSM and Secrets Manager access
aws $PROFILE_ARG iam put-role-policy \
    --role-name $ROLE_NAME \
    --policy-name MCPServerSSMAccess \
    --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["ssm:GetParameter","ssm:GetParameters"],"Resource":"arn:aws:ssm:'"$REGION"':'"$ACCOUNT_ID"':parameter/campaign/*"},{"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":"arn:aws:secretsmanager:'"$REGION"':'"$ACCOUNT_ID"':secret:CampaignRdsStack*"}]}'

echo "✅ IAM permissions added!"

echo ""
echo "============================================================"
echo "NEXT STEPS"
echo "============================================================"
echo "1. Create AgentCore Gateway"
echo "2. Test the MCP server"
echo "3. Integrate with your LangGraph agent"
echo "============================================================"
