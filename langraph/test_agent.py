#!/usr/bin/env python3
"""Test deployed LangGraph Agent"""

import boto3
import json
import uuid
from botocore.config import Config

# Agent ARN from deployment
boto_config = Config(
    connect_timeout=5,
    read_timeout=10,
    retries={'max_attempts': 1}
)
import os as _os
_profile = _os.environ.get('AWS_PROFILE')
_session = boto3.Session(profile_name=_profile, region_name='us-east-1') if _profile else boto3.Session(region_name='us-east-1')
ssm_client = _session.client('ssm', config=boto_config)
AGENT_ARN = ssm_client.get_parameter(Name='/campaign/agent-runtime-arn')['Parameter']['Value']

def test_agent(prompt: str):
    """Call the deployed agent"""
    client = _session.client('bedrock-agentcore')
    
    # Generate unique session ID (must be 33+ chars)
    session_id = f"test-session-{uuid.uuid4()}"
    
    payload = json.dumps({"prompt": prompt})
    
    print(f"Calling agent with prompt: {prompt}")
    print(f"Session ID: {session_id}\n")
    
    response = client.invoke_agent_runtime(
        agentRuntimeArn=AGENT_ARN,
        runtimeSessionId=session_id,
        payload=payload
    )
    
    response_body = response['response'].read()
    response_data = json.loads(response_body)
    
    print("Agent Response:")
    if isinstance(response_data, str):
        print(response_data)
    elif isinstance(response_data, dict) and "response" in response_data:
        print(response_data["response"])
    elif isinstance(response_data, list) and response_data:
        print(response_data[0])
    else:
        print(json.dumps(response_data, indent=2))
    return response_data


if __name__ == "__main__":
    
    print("Test : Query specific campaign")
    print("="*60)
    test_agent("Show me details of campaign with Books category")
