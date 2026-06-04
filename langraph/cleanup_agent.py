#!/usr/bin/env python3
"""
Cleanup LangGraph Agent Runtime from AgentCore
"""

import boto3
import sys

def cleanup_agent():
    """Remove AgentCore Runtime"""
    
    agent_name = "campaign_agent"
    region = "us-east-1"
    
    print(f"Cleaning up agent: {agent_name}")
    
    import os as _os
    _profile = _os.environ.get('AWS_PROFILE')
    _session = boto3.Session(profile_name=_profile, region_name=region) if _profile else boto3.Session(region_name=region)
    client = _session.client('bedrock-agentcore-control')
    
    # Step 1: Get agent ARN from config
    try:
        print("\n1. Reading agent configuration...")
        import yaml
        with open('.bedrock_agentcore.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        agent_config = config['agents'].get(agent_name)
        if not agent_config:
            print(f"❌ Agent {agent_name} not found in config")
            return
        
        agent_arn = agent_config['bedrock_agentcore']['agent_arn']
        agent_runtime_id = agent_arn.split('/')[-1]  # Extract ID from ARN
        print(f"✓ Found agent ARN: {agent_arn}")
        print(f"  Runtime ID: {agent_runtime_id}")
        
    except Exception as e:
        print(f"❌ Failed to read config: {e}")
        return
    
    # Step 2: Delete Runtime
    try:
        print("\n2. Deleting AgentCore Runtime...")
        client.delete_agent_runtime(agentRuntimeId=agent_runtime_id)
        print("✓ Runtime deleted")
        
    except client.exceptions.ResourceNotFoundException:
        print("⚠️  Runtime not found (may already be deleted)")
    except Exception as e:
        print(f"❌ Failed to delete runtime: {e}")
        return
    
    # Step 3: Remove SSM parameter
    try:
        print("\n3. Removing SSM parameter...")
        ssm = _session.client('ssm')
        ssm.delete_parameter(Name='/campaign/agent-runtime-arn')
        print("✓ SSM parameter /campaign/agent-runtime-arn deleted")
    except ssm.exceptions.ParameterNotFound:
        print("⚠️  Parameter not found (may already be deleted)")
    except Exception as e:
        print(f"⚠️  Failed to delete parameter: {e}")

    # Step 4: Remove local AgentCore configuration
    import os
    import shutil

    print("\n4. Removing local configuration...")
    for item in ['.bedrock_agentcore.yaml', '.bedrock_agentcore']:
        try:
            if os.path.isfile(item):
                os.remove(item)
                print(f"✓ Deleted file: {item}")
            elif os.path.isdir(item):
                shutil.rmtree(item)
                print(f"✓ Deleted folder: {item}")
        except Exception as e:
            print(f"⚠️  Could not delete {item}: {e}")
    
    print("\n✅ Cleanup complete!")


if __name__ == "__main__":
    cleanup_agent()

