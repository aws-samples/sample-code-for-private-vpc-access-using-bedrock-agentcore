"""
Shared AWS session helper — supports --profile and --region via env vars or args.

Usage in scripts:
    from aws_session import get_session, get_client

    session = get_session()
    ssm = get_client('ssm')
    cognito = get_client('cognito-idp')

Environment variables (optional):
    AWS_PROFILE  — profile name (default: uses default credential chain)
    AWS_REGION   — region (default: us-east-1)
"""

import os
import boto3

DEFAULT_REGION = "us-east-1"

def get_session(profile=None, region=None):
    """Create a boto3 Session with optional profile and region."""
    p = profile or os.environ.get("AWS_PROFILE")
    r = region or os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION))
    kwargs = {"region_name": r}
    if p:
        kwargs["profile_name"] = p
    return boto3.Session(**kwargs)

def get_client(service, profile=None, region=None, **kwargs):
    """Create a boto3 client with optional profile and region."""
    session = get_session(profile, region)
    return session.client(service, **kwargs)

def get_account_id(profile=None, region=None):
    """Get the current AWS account ID."""
    sts = get_client("sts", profile, region)
    return sts.get_caller_identity()["Account"]

def get_region(profile=None):
    """Get the configured region."""
    session = get_session(profile)
    return session.region_name or DEFAULT_REGION
