import logging

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc

logger = logging.getLogger(__name__)


async def is_feature_enabled(
    request: fastapi.Request,
    project_id: int,
    flag_key: str,
) -> bool:
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.GetFeatureFlags(
            auth_pb2.GetFeatureFlagsRequest(project_id=project_id), timeout=5.0
        )
        for flag in response.flags:
            if flag.key == flag_key:
                return flag.enabled
        return False
    except grpc.RpcError as e:
        logger.warning(f"Feature flag check failed for {flag_key}: {e.details()}")
        return False


async def require_feature_enabled(
    request: fastapi.Request,
    project_id: int,
    flag_key: str,
) -> None:
    enabled = await is_feature_enabled(request, project_id, flag_key)
    if not enabled:
        raise fastapi.HTTPException(
            status_code=403,
            detail=f"Feature '{flag_key}' is not enabled for this project",
        )
