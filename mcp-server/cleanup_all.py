import os as _os
#!/usr/bin/env python3
"""
Cleanup script to remove all Campaign MCP Server resources
Run this to start fresh
"""

import boto3
import sys

def _get_client(service):
    """Create boto3 client respecting AWS_PROFILE env var."""
    profile = _os.environ.get("AWS_PROFILE")
    region = _os.environ.get("AWS_REGION", "us-east-1")
    session = boto3.Session(profile_name=profile, region_name=region) if profile else boto3.Session(region_name=region)
    return session.client(service)

import time

def get_ssm_parameter(name):
    """Get parameter from SSM, return None if not found"""
    ssm = _get_client('ssm')
    try:
        response = ssm.get_parameter(Name=name)
        return response['Parameter']['Value']
    except ssm.exceptions.ParameterNotFound:
        return None
    except Exception as e:
        print(f"Error getting parameter {name}: {e}")
        return None

def remove_gateway_target():
    """Step 1: Remove MCP Server target from Gateway"""
    print("\n" + "="*60)
    print("Step 1: Remove Gateway Target")
    print("="*60)
    
    gateway_id = get_ssm_parameter('/campaign/gateway-id')
    runtime_id = get_ssm_parameter('/campaign/mcp-runtime-id')
    
    if not gateway_id:
        print("⚠️  Gateway ID not found in SSM. Skipping.")
        return
    
    if not runtime_id:
        print("⚠️  Runtime ID not found in SSM. Skipping.")
        return
    
    print(f"Gateway ID: {gateway_id}")
    print(f"Runtime ID: {runtime_id}")
    
    client = _get_client('bedrock-agentcore-control')
    
    try:
        # List targets to find the target ID
        response = client.list_gateway_targets(gatewayIdentifier=gateway_id)
        
        # The key is 'items'
        targets = response.get('items', [])
        
        print(f"Found {len(targets)} targets")
        
        target_id = None
        for target in targets:
            print(f"  - {target.get('name')} (ID: {target.get('targetId')})")
            target_id = target.get('targetId')
            break  # Remove the first target (should only be one)
        
        if not target_id:
            print("⚠️  No targets found in Gateway.")
            return
        
        print(f"\nRemoving target: {target_id}")
        
        client.delete_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id
        )
        
        print("✅ Gateway target removed successfully!")
        
    except Exception as e:
        print(f"❌ Error removing Gateway target: {e}")

def remove_gateway():
    """Step 2: Remove AgentCore Gateway"""
    print("\n" + "="*60)
    print("Step 2: Remove Gateway")
    print("="*60)


def remove_gateway_iam_role():
    """Step 2b: Remove Gateway IAM Role"""
    print("\n" + "="*60)
    print("Step 2b: Remove Gateway IAM Role")
    print("="*60)

    role_name = "campaign-gateway-role"
    iam = _get_client('iam')

    try:
        policies = iam.list_role_policies(RoleName=role_name)
        for policy_name in policies.get('PolicyNames', []):
            iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
            print(f"✓ Deleted inline policy: {policy_name}")

        iam.delete_role(RoleName=role_name)
        print(f"✓ Deleted IAM role: {role_name}")
    except iam.exceptions.NoSuchEntityException:
        print(f"⚠️  Role {role_name} not found (may already be deleted)")
    except Exception as e:
        print(f"❌ Failed to delete role: {e}")
    
    gateway_id = get_ssm_parameter('/campaign/gateway-id')
    
    if not gateway_id:
        print("⚠️  Gateway ID not found in SSM. Skipping.")
        return
    
    print(f"Gateway ID: {gateway_id}")
    
    client = _get_client('bedrock-agentcore-control')
    
    try:
        print("Deleting Gateway...")
        
        client.delete_gateway(gatewayIdentifier=gateway_id)
        
        print("✅ Gateway removed successfully!")
        
    except Exception as e:
        print(f"❌ Error removing Gateway: {e}")

def remove_runtime():
    """Step 3: Remove AgentCore Runtime"""
    print("\n" + "="*60)
    print("Step 3: Remove AgentCore Runtime")
    print("="*60)
    
    runtime_id = get_ssm_parameter('/campaign/mcp-runtime-id')
    
    if not runtime_id:
        print("⚠️  Runtime ID not found in SSM. Skipping.")
        return
    
    print(f"Runtime ID: {runtime_id}")
    
    client = _get_client('bedrock-agentcore-control')
    
    try:
        print("Deleting Runtime...")
        
        client.delete_agent_runtime(agentRuntimeId=runtime_id)
        
        print("✅ Runtime removed successfully!")
        
    except Exception as e:
        print(f"❌ Error removing Runtime: {e}")

def remove_agentcore_sdk_roles():
    """Step 3b: Remove AgentCore SDK auto-created IAM roles"""
    print("\n" + "="*60)
    print("Step 3b: Remove AgentCore SDK Runtime Roles")
    print("="*60)
    
    iam = _get_client('iam')
    
    try:
        paginator = iam.get_paginator('list_roles')
        deleted = []
        for page in paginator.paginate():
            for role in page['Roles']:
                if role['RoleName'].startswith('AmazonBedrockAgentCoreSDKRuntime-'):
                    role_name = role['RoleName']
                    try:
                        # Delete inline policies
                        policies = iam.list_role_policies(RoleName=role_name)
                        for policy_name in policies.get('PolicyNames', []):
                            iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
                        # Detach managed policies
                        attached = iam.list_attached_role_policies(RoleName=role_name)
                        for policy in attached.get('AttachedPolicies', []):
                            iam.detach_role_policy(RoleName=role_name, PolicyArn=policy['PolicyArn'])
                        # Delete role
                        iam.delete_role(RoleName=role_name)
                        deleted.append(role_name)
                        print(f"✓ Deleted: {role_name}")
                    except Exception as e:
                        print(f"⚠️  Could not delete {role_name}: {e}")
        
        if deleted:
            print(f"\n✅ Deleted {len(deleted)} AgentCore SDK roles")
        else:
            print("⚠️  No AgentCore SDK runtime roles found")
    except Exception as e:
        print(f"❌ Error listing roles: {e}")

def remove_identity_credential_provider():
    """Step 4: Remove Identity Credential Provider"""
    print("\n" + "="*60)
    print("Step 4: Remove Identity Credential Provider")
    print("="*60)
    
    provider_arn = get_ssm_parameter('/campaign/gateway-credential-provider-arn')
    
    if not provider_arn:
        print("⚠️  Credential Provider ARN not found in SSM. Skipping.")
        return
    
    # Extract provider name from ARN
    provider_name = provider_arn.split('/')[-1]
    print(f"Provider Name: {provider_name}")
    
    client = _get_client('bedrock-agentcore-control')
    
    try:
        print("Deleting Identity Credential Provider...")
        
        client.delete_oauth2_credential_provider(name=provider_name)
        
        print("✅ Identity Credential Provider removed successfully!")
        
    except Exception as e:
        print(f"❌ Error removing Identity Credential Provider: {e}")

def remove_runtime_cognito():
    """Step 5: Remove Runtime Cognito User Pool"""
    print("\n" + "="*60)
    print("Step 5: Remove Runtime Cognito User Pool")
    print("="*60)
    
    pool_id = get_ssm_parameter('/campaign/mcp-runtime-user-pool-id')
    
    if not pool_id:
        print("⚠️  Runtime User Pool ID not found in SSM. Skipping.")
        return
    
    print(f"User Pool ID: {pool_id}")
    
    cognito = _get_client('cognito-idp')
    
    try:
        # Delete domain first if exists
        pool_info = cognito.describe_user_pool(UserPoolId=pool_id)
        domain = pool_info.get('UserPool', {}).get('Domain')
        if domain:
            print(f"Deleting domain: {domain}")
            cognito.delete_user_pool_domain(Domain=domain, UserPoolId=pool_id)
        
        print("Deleting User Pool...")
        cognito.delete_user_pool(UserPoolId=pool_id)
        
        print("✅ Runtime Cognito User Pool removed successfully!")
        
    except Exception as e:
        print(f"❌ Error removing Runtime Cognito: {e}")

def remove_gateway_cognito():
    """Step 6: Remove Gateway Cognito User Pool"""
    print("\n" + "="*60)
    print("Step 6: Remove Gateway Cognito User Pool")
    print("="*60)
    
    pool_id = get_ssm_parameter('/campaign/gateway-user-pool-id')
    
    if not pool_id:
        print("⚠️  Gateway User Pool ID not found in SSM. Skipping.")
        return
    
    print(f"User Pool ID: {pool_id}")
    
    cognito = _get_client('cognito-idp')
    
    try:
        # Delete domain first if exists
        pool_info = cognito.describe_user_pool(UserPoolId=pool_id)
        domain = pool_info.get('UserPool', {}).get('Domain')
        if domain:
            print(f"Deleting domain: {domain}")
            cognito.delete_user_pool_domain(Domain=domain, UserPoolId=pool_id)
        
        print("Deleting User Pool...")
        cognito.delete_user_pool(UserPoolId=pool_id)
        
        print("✅ Gateway Cognito User Pool removed successfully!")
        
    except Exception as e:
        print(f"❌ Error removing Gateway Cognito: {e}")

def remove_ssm_parameters():
    """Step 7: Remove SSM Parameters"""
    print("\n" + "="*60)
    print("Step 7: Remove SSM Parameters")
    print("="*60)
    
    ssm = _get_client('ssm')
    
    # Only delete AgentCore-related parameters
    agentcore_params = [
        '/campaign/gateway-id',
        '/campaign/gateway-url',
        '/campaign/gateway-client-id',
        '/campaign/gateway-client-secret',
        '/campaign/gateway-scope',
        '/campaign/gateway-user-pool-id',
        '/campaign/gateway-credential-provider-arn',
        '/campaign/gateway-target-id',
        '/campaign/mcp-runtime-id',
        '/campaign/mcp-runtime-arn',
        '/campaign/mcp-runtime-user-pool-id',
        '/campaign/mcp-runtime-client-id',
        '/campaign/mcp-runtime-client-secret',
        '/campaign/mcp-runtime-discovery-url',
        '/campaign/mcp-runtime-scope'
    ]
    
    deleted = []
    for param in agentcore_params:
        try:
            ssm.delete_parameter(Name=param)
            deleted.append(param)
            print(f"✓ Deleted: {param}")
        except (ssm.exceptions.ParameterNotFound, Exception) as e:
            print(f"  Skipped: {param} ({e})")
    
    if deleted:
        print(f"\n✅ Deleted {len(deleted)} SSM parameters")
    else:
        print("⚠️  No SSM parameters found")
    
    print("\nKept infrastructure parameters:")
    print("  /campaign/vpc-id")
    print("  /campaign/private-subnet-ids")
    print("  /campaign/mcp-sg-id")
    print("  /campaign/rds-sg-id")
    print("  /campaign/db-endpoint")
    print("  /campaign/db-credentials-arn")

def remove_local_config():
    """Step 8: Remove Local AgentCore Configuration"""
    print("\n" + "="*60)
    print("Step 8: Remove Local AgentCore Configuration")
    print("="*60)
    
    import os
    import shutil
    
    files_to_remove = [
        '.bedrock_agentcore.yaml',
        '.bedrock_agentcore'
    ]
    
    for item in files_to_remove:
        try:
            if os.path.isfile(item):
                os.remove(item)
                print(f"✓ Deleted file: {item}")
            elif os.path.isdir(item):
                shutil.rmtree(item)
                print(f"✓ Deleted folder: {item}")
        except Exception as e:
            print(f"⚠️  Could not delete {item}: {e}")
    
    print("✅ Local configuration cleaned up!")

def main():
    print("="*60)
    print("Campaign MCP Server Cleanup")
    print("="*60)
    print("\nThis will remove all Campaign MCP Server resources.")
    print("Resources to be removed:")
    print("  1. Gateway Target")
    print("  2. AgentCore Gateway")
    print("  3. AgentCore Runtime")
    print("  3b. AgentCore SDK Runtime Roles")
    print("  4. Identity Credential Provider")
    print("  5. Runtime Cognito Pool")
    print("  6. Gateway Cognito Pool")
    print("  7. SSM Parameters")
    print("  8. Local AgentCore Configuration")
    
    response = input("\nContinue? (yes/no): ").strip().lower()
    if response != 'yes':
        print("Cleanup cancelled.")
        sys.exit(0)
    
    # Step 1: Remove Gateway Target
    remove_gateway_target()

    time.sleep(30)
    
    # Step 2: Remove Gateway
    remove_gateway()
    
    # Step 2b: Remove Gateway IAM Role
    remove_gateway_iam_role()
    
    # Step 3: Remove Runtime
    remove_runtime()
    
    # Step 3b: Remove AgentCore SDK Runtime Roles
    remove_agentcore_sdk_roles()
    
    # Step 4: Remove Identity Credential Provider
    remove_identity_credential_provider()
    
    # Step 5: Remove Runtime Cognito
    remove_runtime_cognito()
    
    # Step 6: Remove Gateway Cognito
    remove_gateway_cognito()
    
    # Step 7: Remove SSM Parameters
    remove_ssm_parameters()
    
    # Step 8: Remove Local Configuration
    remove_local_config()
    
    print("\n" + "="*60)
    print("✅ All Cleanup Complete!")
    print("="*60)
    print("\nAll AgentCore resources have been removed.")
    print("Infrastructure (VPC, RDS, etc.) is preserved.")

if __name__ == "__main__":
    main()
