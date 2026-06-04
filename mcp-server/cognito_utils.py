"""Shared Cognito utility functions for user pool, resource server, and M2M client management."""


def get_or_create_user_pool(cognito, user_pool_name):
    """Get existing user pool by name or create a new one with OAuth domain."""
    response = cognito.list_user_pools(MaxResults=60)
    for pool in response["UserPools"]:
        if pool["Name"] == user_pool_name:
            return pool["Id"]

    print('Creating new user pool')
    created = cognito.create_user_pool(PoolName=user_pool_name)
    user_pool_id = created["UserPool"]["Id"]
    domain = user_pool_id.replace("_", "").lower()
    cognito.create_user_pool_domain(Domain=domain, UserPoolId=user_pool_id)
    print("Domain created as well")
    return user_pool_id


def get_or_create_resource_server(cognito, user_pool_id, resource_server_id, resource_server_name, scopes):
    """Ensure a resource server exists on the user pool."""
    try:
        cognito.describe_resource_server(UserPoolId=user_pool_id, Identifier=resource_server_id)
        return resource_server_id
    except cognito.exceptions.ResourceNotFoundException:
        print('Creating new resource server')
        cognito.create_resource_server(
            UserPoolId=user_pool_id,
            Identifier=resource_server_id,
            Name=resource_server_name,
            Scopes=scopes
        )
        return resource_server_id


def get_or_create_m2m_client(cognito, user_pool_id, client_name, resource_server_id, scopes=None):
    """Get existing M2M client or create a new one with client_credentials flow."""
    response = cognito.list_user_pool_clients(UserPoolId=user_pool_id, MaxResults=60)
    for client in response["UserPoolClients"]:
        if client["ClientName"] == client_name:
            describe = cognito.describe_user_pool_client(
                UserPoolId=user_pool_id, ClientId=client["ClientId"]
            )
            return client["ClientId"], describe["UserPoolClient"]["ClientSecret"]

    print('Creating new m2m client')
    if scopes is None:
        scopes = [f"{resource_server_id}/invoke"]

    created = cognito.create_user_pool_client(
        UserPoolId=user_pool_id,
        ClientName=client_name,
        GenerateSecret=True,
        AllowedOAuthFlows=["client_credentials"],
        AllowedOAuthScopes=scopes,
        AllowedOAuthFlowsUserPoolClient=True,
        SupportedIdentityProviders=["COGNITO"],
        ExplicitAuthFlows=["ALLOW_REFRESH_TOKEN_AUTH"]
    )
    return created["UserPoolClient"]["ClientId"], created["UserPoolClient"]["ClientSecret"]
