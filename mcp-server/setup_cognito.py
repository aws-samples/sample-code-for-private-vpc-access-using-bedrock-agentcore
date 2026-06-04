import argparse
from aws_session import get_session, get_client, get_region
#!/usr/bin/env python3
"""
Setup Cognito authentication for MCP Server Runtime
Based on: https://github.com/awslabs/amazon-bedrock-agentcore-samples
"""

from cognito_utils import get_or_create_user_pool, get_or_create_resource_server, get_or_create_m2m_client

# Main setup: create runtime pool to protect MCP server, it will be used when gateway is calling mcp server
# Parse --profile arg
_parser = argparse.ArgumentParser(add_help=False)
_parser.add_argument('--profile', default=None)
_args, _ = _parser.parse_known_args()

REGION = get_region(_args.profile)
USER_POOL_NAME = "campaign-mcp-runtime-pool"
RESOURCE_SERVER_ID = "campaign-mcp-runtime"
RESOURCE_SERVER_NAME = "Campaign MCP Runtime"
CLIENT_NAME = "campaign-mcp-runtime-client"
SCOPES = [
    {
        "ScopeName": "invoke",
        "ScopeDescription": "Invoke MCP server"
    }
]

scope_names = [f"{RESOURCE_SERVER_ID}/{scope['ScopeName']}" for scope in SCOPES]
scope_string = " ".join(scope_names)

cognito = get_client("cognito-idp", _args.profile)
ssm = get_client("ssm", _args.profile)

print("=== Creating or retrieving Cognito resources ===")
runtime_user_pool_id = get_or_create_user_pool(cognito, USER_POOL_NAME)
print(f"User Pool ID: {runtime_user_pool_id}")

get_or_create_resource_server(cognito, runtime_user_pool_id, RESOURCE_SERVER_ID, RESOURCE_SERVER_NAME, SCOPES)
print("Resource server ensured.")

runtime_client_id, runtime_client_secret = get_or_create_m2m_client(
    cognito, runtime_user_pool_id, CLIENT_NAME, RESOURCE_SERVER_ID, scope_names
)

print(f"Client ID: {runtime_client_id}")

# Get discovery URL
runtime_cognito_discovery_url = f'https://cognito-idp.{REGION}.amazonaws.com/{runtime_user_pool_id}/.well-known/openid-configuration'
print(f"Discovery URL: {runtime_cognito_discovery_url}")
print(f"Scope: {scope_string}")

# Save to Parameter Store
print("\n=== Saving to Parameter Store ===")
ssm.put_parameter(Name="/campaign/mcp-runtime-user-pool-id", Value=runtime_user_pool_id, Type="String", Overwrite=True)
ssm.put_parameter(Name="/campaign/mcp-runtime-client-id", Value=runtime_client_id, Type="String", Overwrite=True)
ssm.put_parameter(Name="/campaign/mcp-runtime-client-secret", Value=runtime_client_secret, Type="SecureString", Overwrite=True)
ssm.put_parameter(Name="/campaign/mcp-runtime-discovery-url", Value=runtime_cognito_discovery_url, Type="String", Overwrite=True)
ssm.put_parameter(Name="/campaign/mcp-runtime-scope", Value=scope_string, Type="String", Overwrite=True)

print("✅ Cognito configuration saved to Parameter Store")
