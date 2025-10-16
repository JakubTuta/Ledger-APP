import grpc


def create_grpc_error(code: grpc.StatusCode, message: str) -> grpc.RpcError:
    error = grpc.RpcError()
    error.code = lambda: code
    error.details = lambda: message
    return error


def create_api_key_cache_data(
    project_id: int = 1,
    account_id: int = 1,
    rate_limit_per_minute: int = 1000,
    rate_limit_per_hour: int = 50000,
    daily_quota: int = 1000000,
    current_usage: int = 0,
) -> dict:
    return {
        "project_id": project_id,
        "account_id": account_id,
        "rate_limit_per_minute": rate_limit_per_minute,
        "rate_limit_per_hour": rate_limit_per_hour,
        "daily_quota": daily_quota,
        "current_usage": current_usage,
    }
