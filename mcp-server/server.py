#!/usr/bin/env python3
"""Amazon Ads Campaign MCP Server - PostgreSQL integration for campaign data analysis"""

from mcp.server.fastmcp import FastMCP
from typing import Annotated, List, Dict, Any
from pydantic import Field
import asyncpg
import boto3
import json
from botocore.exceptions import ClientError
from botocore.config import Config

import re
import time

# Initialize the FastMCP server with correct configuration for AgentCore Runtime
mcp = FastMCP(host="0.0.0.0", stateless_http=True)

# Configure boto3 with shorter timeouts and fewer retries
boto_config = Config(
    connect_timeout=5,
    read_timeout=10,
    retries={'max_attempts': 1}
)

# Initialize AWS clients
ssm_client = boto3.client('ssm', region_name='us-east-1', config=boto_config)
secrets_client = boto3.client('secretsmanager', region_name='us-east-1', config=boto_config)

# Credential cache with TTL (M2)
_cred_cache = {"value": None, "expiry": 0}


def get_db_credentials():
    """Fetch database credentials with 5-minute TTL cache."""
    if _cred_cache["value"] and time.time() < _cred_cache["expiry"]:
        return _cred_cache["value"]
    try:
        db_endpoint = ssm_client.get_parameter(Name='/campaign/db-endpoint')['Parameter']['Value']
        connection_string = (
            f"postgresql://mcp_readonly:mcp_readonly_temp"
            f"@{db_endpoint}:5432/campaigndb?sslmode=require"
        )
        _cred_cache["value"] = connection_string
        _cred_cache["expiry"] = time.time() + 300
        return connection_string
    except ClientError as e:
        raise Exception(f"Failed to retrieve database credentials: {e}")


# Connection pool (lazy init)
_pool = None


async def get_pool():
    """Get or create the database connection pool."""
    global _pool
    if _pool is None:
        connection_string = get_db_credentials()
        _pool = await asyncpg.create_pool(connection_string, min_size=2, max_size=10, command_timeout=30)
    return _pool


@mcp.tool()
async def list_tables() -> List[str]:
    """List all tables in the connected PostgreSQL database"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """
        rows = await conn.fetch(query)
        return [row['table_name'] for row in rows]


@mcp.tool()
async def describe_table(
    table_name: Annotated[str, Field(description="Name of the table to describe")]
) -> List[Dict[str, Any]]:
    """Get column information for a specific table"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        query = """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = $1
            ORDER BY ordinal_position
        """
        rows = await conn.fetch(query, table_name)
        return [dict(row) for row in rows]


@mcp.tool()
async def execute_query(
    query: Annotated[str, Field(description="SQL query to execute (read-only SELECT only)")]
) -> List[Dict[str, Any]]:
    """Execute a read-only SQL query against the PostgreSQL database"""
    query_stripped = query.strip().rstrip(';').strip()

    # Reject multiple statements (prevents SQL injection via semicolons)
    if ';' in query_stripped:
        raise ValueError("Multiple statements are not allowed")

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Defense-in-depth: read-only transaction + read-only database user
        async with conn.transaction(readonly=True):
            rows = await conn.fetch(query_stripped, timeout=10)
            return [dict(row) for row in rows[:1000]]  # Limit results


# Run the server
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
