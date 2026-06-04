import argparse as _ap
from aws_session import get_client, get_region, get_account_id
#!/usr/bin/env python3
"""
Add MCP Server as Gateway Target
Based on: https://github.com/awslabs/amazon-bedrock-agentcore-samples
"""

import boto3

_p = _ap.ArgumentParser(add_help=False); _p.add_argument('--profile', default=None); _a, _ = _p.parse_known_args()
REGION = get_region(_a.profile)
ssm = get_client('ssm', _a.profile)
gateway_client = get_client('bedrock-agentcore-control', _a.profile)
identity_client = get_client('bedrock-agentcore-control', _a.profile)

print("=== Step 1: Get Configuration from Parameter Store ===")
# Gateway config
gateway_id = ssm.get_parameter(Name='/campaign/gateway-id')['Parameter']['Value']
gateway_url = ssm.get_parameter(Name='/campaign/gateway-url')['Parameter']['Value']

# MCP Runtime config
runtime_arn = ssm.get_parameter(Name='/campaign/mcp-runtime-arn')['Parameter']['Value']
runtime_client_id = ssm.get_parameter(Name='/campaign/mcp-runtime-client-id')['Parameter']['Value']
runtime_client_secret = ssm.get_parameter(Name='/campaign/mcp-runtime-client-secret', WithDecryption=True)['Parameter']['Value']
runtime_discovery_url = ssm.get_parameter(Name='/campaign/mcp-runtime-discovery-url')['Parameter']['Value']
runtime_scope = ssm.get_parameter(Name='/campaign/mcp-runtime-scope')['Parameter']['Value']

print(f"Gateway ID: {gateway_id}")
print(f"Runtime ARN: {runtime_arn}")

# Build MCP server endpoint URL
account_id = get_account_id(_a.profile)
encoded_arn = runtime_arn.replace(':', '%3A').replace('/', '%2F')
agent_url = f'https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT'

print(f"MCP Server URL: {agent_url}")

print("\n=== Step 2: Create Identity Credential Provider ===")
# Create OAuth2 credential provider for Gateway to authenticate with MCP Server
# this is for creating an AgentCore Identity for saving runtime pool (client ID + Secret) 
# will be used when Gateway need access to MCP server
try:
    cognito_provider = identity_client.create_oauth2_credential_provider(
        name="campaign-gateway-mcp-identity",
        credentialProviderVendor="CustomOauth2",
        oauth2ProviderConfigInput={
            'customOauth2ProviderConfig': {
                'oauthDiscovery': {
                    'discoveryUrl': runtime_discovery_url,
                },
                'clientId': runtime_client_id,
                'clientSecret': runtime_client_secret
            }
        }
    )
    cognito_provider_arn = cognito_provider['credentialProviderArn']
    print(f"Created credential provider: {cognito_provider_arn}")
except Exception as e:
    if "ResourceConflictException" in str(e):
        # Get existing provider
        providers = identity_client.list_oauth2_credential_providers(maxResults=100)
        cognito_provider_arn = next(
            p['credentialProviderArn'] for p in providers['items'] 
            if p['name'] == "campaign-gateway-mcp-identity"
        )
        print(f"Using existing credential provider: {cognito_provider_arn}")
    else:
        raise

print("\n=== Step 3: Create Gateway Target ===")
# this is to tell Gateway where to find this targeting MCP server
create_gateway_target_response = gateway_client.create_gateway_target(
    name='campaign-mcp-server-target',
    gatewayIdentifier=gateway_id,
    targetConfiguration={
        'mcp': {
            'mcpServer': {
                'endpoint': agent_url # this is the location of the MCP server
            }
        }
    },
    credentialProviderConfigurations=[ # this is where to find the credential and which scope
        {
            'credentialProviderType': 'OAUTH',
            'credentialProvider': {
                'oauthCredentialProvider': {
                    'providerArn': cognito_provider_arn,
                    'scopes': [runtime_scope]
                }
            }
        }
    ]
)

target_id = create_gateway_target_response['targetId']
print(f"\n✅ Gateway target created successfully!")
print(f"Target ID: {target_id}")

# Save to Parameter Store
ssm.put_parameter(Name='/campaign/gateway-target-id', Value=target_id, Type='String', Overwrite=True)
ssm.put_parameter(Name='/campaign/gateway-credential-provider-arn', Value=cognito_provider_arn, Type='String', Overwrite=True)

print("\n=== Step 4: Wait for Target to be Ready ===")
import time
MAX_WAIT = 120
WAIT_INTERVAL = 10
elapsed = 0

while elapsed < MAX_WAIT:
    targets = gateway_client.list_gateway_targets(gatewayIdentifier=gateway_id)
    target = next((t for t in targets['items'] if t['targetId'] == target_id), None)
    status = target['status'] if target else 'NOT_FOUND'
    print(f"  Target status: {status} ({elapsed}s elapsed)")

    if status in ('ACTIVE', 'READY'):
        print("✅ Gateway target is ready!")
        break
    elif status == 'FAILED':
        print("⚠️  Target sync failed. Retrying sync...")
        gateway_client.synchronize_gateway_targets(gatewayIdentifier=gateway_id, targetIdList=[target_id])
    time.sleep(WAIT_INTERVAL)
    elapsed += WAIT_INTERVAL

if status not in ('ACTIVE', 'READY'):
    print(f"⚠️  Target not ACTIVE after {MAX_WAIT}s. Check the AgentCore Gateway console.")

print("\n" + "="*60)
print("SETUP COMPLETE!")
print("="*60)
print(f"Gateway URL: {gateway_url}")
print(f"Target: campaign-mcp-server-target")
print(f"Target Status: {status}")
print("\nNext: Test the gateway with an agent")
print("="*60)
