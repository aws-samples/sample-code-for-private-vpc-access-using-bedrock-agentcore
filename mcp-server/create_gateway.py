import argparse as _ap
from aws_session import get_session, get_client, get_region, get_account_id
#!/usr/bin/env python3
"""
Create AgentCore Gateway for MCP Server
Based on: https://github.com/awslabs/amazon-bedrock-agentcore-samples
"""

import boto3
import json
import time

_p = _ap.ArgumentParser(add_help=False); _p.add_argument('--profile', default=None); _a, _ = _p.parse_known_args()
REGION = get_region(_a.profile)
ssm = get_client('ssm', _a.profile)
gateway_client = get_client('bedrock-agentcore-control', _a.profile)

print("=== Step 1: Get MCP Runtime Configuration ===")
runtime_user_pool_id = ssm.get_parameter(Name='/campaign/mcp-runtime-user-pool-id')['Parameter']['Value']
runtime_client_id = ssm.get_parameter(Name='/campaign/mcp-runtime-client-id')['Parameter']['Value']
runtime_discovery_url = ssm.get_parameter(Name='/campaign/mcp-runtime-discovery-url')['Parameter']['Value']

print(f"Runtime User Pool ID: {runtime_user_pool_id}")
print(f"Runtime Client ID: {runtime_client_id}")

print("\n=== Step 2: Create Gateway Cognito Pool ===") # gateway pool is to protect gateway and will be used when agent is calling agentcore gateway
# Import shared Cognito utilities
from cognito_utils import get_or_create_user_pool, get_or_create_resource_server, get_or_create_m2m_client

# Create Gateway Cognito pool
cognito = get_client('cognito-idp', _a.profile)
GW_USER_POOL_NAME = "campaign-gateway-pool"
GW_RESOURCE_SERVER_ID = "campaign-gateway"
GW_RESOURCE_SERVER_NAME = "Campaign Gateway"
GW_CLIENT_NAME = "campaign-gateway-client"
GW_SCOPES = [{"ScopeName": "invoke", "ScopeDescription": "Invoke gateway"}]

gw_scope_names = [f"{GW_RESOURCE_SERVER_ID}/{scope['ScopeName']}" for scope in GW_SCOPES]
gw_scope_string = " ".join(gw_scope_names)

gw_user_pool_id = get_or_create_user_pool(cognito, GW_USER_POOL_NAME)
print(f"Gateway User Pool ID: {gw_user_pool_id}")

get_or_create_resource_server(cognito, gw_user_pool_id, GW_RESOURCE_SERVER_ID, GW_RESOURCE_SERVER_NAME, GW_SCOPES)
gw_client_id, gw_client_secret = get_or_create_m2m_client(cognito, gw_user_pool_id, GW_CLIENT_NAME, GW_RESOURCE_SERVER_ID, gw_scope_names)

gw_cognito_discovery_url = f'https://cognito-idp.{REGION}.amazonaws.com/{gw_user_pool_id}/.well-known/openid-configuration'
print(f"Gateway Client ID: {gw_client_id}")
print(f"Gateway Discovery URL: {gw_cognito_discovery_url}")

print("\n=== Step 3: Create IAM Role for Gateway ===")
iam_client = get_client('iam', _a.profile)
account_id = get_account_id(_a.profile)
gateway_role_name = "campaign-gateway-role"

role_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetResourceOauth2Token",
                "bedrock-agentcore:SynchronizeGatewayTargets",
                "bedrock-agentcore:GetGateway",
                "bedrock-agentcore:GetGatewayTarget",
                "bedrock-agentcore:ListGatewayTargets",
                "bedrock-agentcore:GetResourcePolicy",
                "bedrock-agentcore:ListTagsForResource",
                "bedrock-agentcore:ListPolicyEngines",
                "bedrock-agentcore:InvokeGateway",
                "bedrock-agentcore:GetAgentRuntime",
                "bedrock-agentcore:GetAgentRuntimeEndpoint",
                "bedrock-agentcore:ListAgentRuntimes",
                "bedrock-agentcore:ListAgentRuntimeEndpoints",
                "bedrock-agentcore:ListAgentRuntimeVersions"
            ],
            "Resource": f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:*"
        },
        {
            "Effect": "Allow",
            "Action": "bedrock:InvokeModel",
            "Resource": f"arn:aws:bedrock:{REGION}::foundation-model/*"
        },
        {
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": f"arn:aws:iam::{account_id}:role/campaign-gateway-role"
        },
        {
            "Effect": "Allow",
            "Action": "secretsmanager:GetSecretValue",
            "Resource": f"arn:aws:secretsmanager:{REGION}:{account_id}:secret:*"
        }
    ]
}

assume_role_policy = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole",
        "Condition": {
            "StringEquals": {"aws:SourceAccount": account_id},
            "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock-agentcore:{REGION}:{account_id}:*"}
        }
    }]
}

try:
    role_response = iam_client.create_role(
        RoleName=gateway_role_name,
        AssumeRolePolicyDocument=json.dumps(assume_role_policy)
    )
    time.sleep(10)
    print(f"Created IAM role: {gateway_role_name}")
except iam_client.exceptions.EntityAlreadyExistsException:
    role_response = iam_client.get_role(RoleName=gateway_role_name)
    print(f"Using existing IAM role: {gateway_role_name}")

iam_client.put_role_policy(
    RoleName=gateway_role_name,
    PolicyName="GatewayPolicy",
    PolicyDocument=json.dumps(role_policy)
)

gateway_role_arn = role_response['Role']['Arn']
print(f"Gateway Role ARN: {gateway_role_arn}")

print("\n=== Step 4: Create Gateway ===")
auth_config = {
    "customJWTAuthorizer": {
        "allowedClients": [gw_client_id],
        "discoveryUrl": gw_cognito_discovery_url
    }
}

create_response = gateway_client.create_gateway(
    name='campaign-gateway',
    roleArn=gateway_role_arn,
    protocolType='MCP',
    protocolConfiguration={
        'mcp': {
            'supportedVersions': ['2025-03-26'],
            'searchType': 'SEMANTIC'
        }
    },
    authorizerType='CUSTOM_JWT',
    authorizerConfiguration=auth_config,
    description='Campaign MCP Gateway'
)

gateway_id = create_response["gatewayId"]
gateway_url = create_response["gatewayUrl"]

print(f"\n✅ Gateway created successfully!")
print(f"Gateway ID: {gateway_id}")
print(f"Gateway URL: {gateway_url}")

# Save to Parameter Store
print("\n=== Step 5: Save Gateway Configuration ===")
ssm.put_parameter(Name='/campaign/gateway-id', Value=gateway_id, Type='String', Overwrite=True)
ssm.put_parameter(Name='/campaign/gateway-url', Value=gateway_url, Type='String', Overwrite=True)
ssm.put_parameter(Name='/campaign/gateway-user-pool-id', Value=gw_user_pool_id, Type='String', Overwrite=True)
ssm.put_parameter(Name='/campaign/gateway-client-id', Value=gw_client_id, Type='String', Overwrite=True)
ssm.put_parameter(Name='/campaign/gateway-client-secret', Value=gw_client_secret, Type='SecureString', Overwrite=True)
ssm.put_parameter(Name='/campaign/gateway-scope', Value=gw_scope_string, Type='String', Overwrite=True)

print("✅ Configuration saved to Parameter Store")
