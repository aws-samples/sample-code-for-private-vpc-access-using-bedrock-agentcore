#!/usr/bin/env python3
"""
LangGraph Agent calling MCP Server via AgentCore Gateway
"""

import boto3
import requests
import logging
import time
from typing import Dict, Any
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from langchain_aws import ChatBedrock
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()

# Global agent (lazy init)
_agent = None
_mcp_client = None


class MCPGatewayClient:
    """MCP Gateway client"""
    
    def __init__(self):
        self.gateway_url = None
        self.token = None
        self.token_expiry = 0
        self._initialized = False
    
    def _ensure_initialized(self):
        if self._initialized and time.time() < self.token_expiry - 60:
            return
        
        ssm = boto3.client('ssm', region_name='us-east-1')
        
        params = ssm.get_parameters(
            Names=[
                '/campaign/gateway-url',
                '/campaign/gateway-client-id',
                '/campaign/gateway-user-pool-id'
            ]
        )
        param_dict = {p['Name']: p['Value'] for p in params['Parameters']}
        
        self.gateway_url = param_dict['/campaign/gateway-url']
        client_id = param_dict['/campaign/gateway-client-id']
        gateway_pool_id = param_dict['/campaign/gateway-user-pool-id']
        
        client_secret = ssm.get_parameter(
            Name='/campaign/gateway-client-secret',
            WithDecryption=True
        )['Parameter']['Value']
        
        # Get OAuth token
        domain = gateway_pool_id.replace('_', '').lower()
        token_url = f"https://{domain}.auth.us-east-1.amazoncognito.com/oauth2/token"
        
        response = requests.post(
            token_url,
            auth=(client_id, client_secret),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={'grant_type': 'client_credentials', 'scope': 'campaign-gateway/invoke'},
            timeout=10
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get token: {response.text}")
        
        self.token = response.json()['access_token']
        self.token_expiry = time.time() + response.json().get('expires_in', 3600)
        self._initialized = True
    
    def _jsonrpc(self, method: str, params: dict = None, timeout: int = 10):
        """Send JSON-RPC request to MCP gateway"""
        self._ensure_initialized()
        payload = {"jsonrpc": "2.0", "method": method, "id": 1}
        if params:
            payload["params"] = params
        response = requests.post(
            self.gateway_url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout
        )
        if response.status_code != 200:
            raise Exception(f"MCP {method} failed: {response.text}")
        result = response.json()
        if "error" in result:
            raise Exception(f"MCP {method} error: {result['error']}")
        return result.get("result", {})

    def list_tools(self):
        return self._jsonrpc("tools/list").get('tools', [])
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        result = self._jsonrpc("tools/call", {"name": tool_name, "arguments": arguments}, timeout=30)
        if 'content' in result and isinstance(result['content'], list):
            for item in result['content']:
                if item.get('type') == 'text':
                    return item.get('text', str(result))
        return str(result)


def create_tools(mcp_client: MCPGatewayClient):
    """Create LangChain tools from MCP tools"""
    mcp_tools = mcp_client.list_tools()
    langchain_tools = []
    
    for mcp_tool in mcp_tools:
        tool_name = mcp_tool['name']
        tool_desc = mcp_tool.get('description', f'MCP tool: {tool_name}')
        
        def make_tool(name, desc):
            @tool(name, description=desc)
            def mcp_tool_wrapper(query: str) -> str:
                try:
                    return mcp_client.call_tool(name, {"query": query})
                except Exception as e:
                    return f"Error: {str(e)}"
            return mcp_tool_wrapper
        
        langchain_tools.append(make_tool(tool_name, tool_desc))
    
    return langchain_tools


def _initialize_agent():
    """Lazy initialization"""
    global _agent, _mcp_client
    
    if _agent is not None:
        return _agent
    
    logger.info("Initializing agent...")
    
    _mcp_client = MCPGatewayClient()
    tools = create_tools(_mcp_client)
    
    llm = ChatBedrock(
        model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        region_name="us-east-1",
        model_kwargs={"temperature": 0.1}
    )
    
    system_prompt = """You are a helpful AI assistant with access to campaign database tools."""
    _agent = create_react_agent(llm, tools, prompt=system_prompt)
    
    logger.info("Agent ready")
    return _agent


@app.entrypoint
def invoke_agent(payload):
    """Main agent entrypoint — called by AgentCore Runtime"""
    text = payload.get("prompt", "")
    logger.info(f"Request: {text[:100]}...")
    
    agent = _initialize_agent()
    result = agent.invoke({"messages": [HumanMessage(content=text)]})
    response_text = result["messages"][-1].content if result.get("messages") else "No response"
    
    logger.info(f"Response: {response_text[:100]}...")
    return response_text


if __name__ == "__main__":
    app.run()
