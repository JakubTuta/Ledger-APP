import logging

import fastapi
import gateway_service.proto.auth_pb2 as auth_pb2
import gateway_service.proto.auth_pb2_grpc as auth_pb2_grpc
import grpc
from pydantic import BaseModel

router = fastapi.APIRouter(tags=["Feature Flags"])
logger = logging.getLogger(__name__)


def _require_account(request: fastapi.Request) -> int:
    account_id = getattr(request.state, "account_id", None)
    if not account_id:
        raise fastapi.HTTPException(status_code=401, detail="Authentication required")
    return account_id


class FeatureFlagResponse(BaseModel):
    key: str
    enabled: bool


class SetFeatureFlagRequest(BaseModel):
    key: str
    enabled: bool


@router.get(
    "/projects/{project_id}/feature-flags",
    response_model=list[FeatureFlagResponse],
    summary="Get feature flags for a project",
)
async def get_feature_flags(
    project_id: int, request: fastapi.Request
) -> list[FeatureFlagResponse]:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.GetFeatureFlags(
            auth_pb2.GetFeatureFlagsRequest(project_id=project_id), timeout=5.0
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return [FeatureFlagResponse(key=f.key, enabled=f.enabled) for f in response.flags]


@router.put(
    "/projects/{project_id}/feature-flags",
    response_model=FeatureFlagResponse,
    summary="Set a feature flag for a project",
)
async def set_feature_flag(
    project_id: int,
    payload: SetFeatureFlagRequest,
    request: fastapi.Request,
) -> FeatureFlagResponse:
    _require_account(request)
    grpc_pool = request.app.state.grpc_pool
    try:
        channel = grpc_pool.get_channel("auth")
        stub = auth_pb2_grpc.AuthServiceStub(channel)
        response = await stub.SetFeatureFlag(
            auth_pb2.SetFeatureFlagRequest(
                project_id=project_id, key=payload.key, enabled=payload.enabled
            ),
            timeout=5.0,
        )
    except grpc.RpcError as e:
        raise fastapi.HTTPException(status_code=502, detail=str(e.details()))
    return FeatureFlagResponse(key=response.flag.key, enabled=response.flag.enabled)
