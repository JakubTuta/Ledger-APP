import datetime
import logging

import fastapi
import gateway_service.config as config
import gateway_service.proto.auth_pb2 as auth_pb2
import grpc

router = fastapi.APIRouter(tags=["settings"])
logger = logging.getLogger(__name__)


@router.get("/settings")
async def get_settings(request: fastapi.Request):
    grpc_pool = request.app.state.grpc_pool
    project_id = request.state.project_id

    try:
        async with grpc_pool.get_auth_stub() as stub:
            project_response = await stub.GetProjectById(
                auth_pb2.GetProjectByIdRequest(project_id=project_id),
                timeout=config.settings.GRPC_TIMEOUT,
            )

            usage_response = await stub.GetDailyUsage(
                auth_pb2.GetDailyUsageRequest(
                    project_id=project_id, date=datetime.date.today().isoformat()
                ),
                timeout=config.settings.GRPC_TIMEOUT,
            )

        quota_remaining = project_response.daily_quota - usage_response.log_count
        tomorrow = datetime.datetime.now(datetime.timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(days=1)

        return {
            "project_id": project_id,
            "project_name": project_response.name,
            "project_slug": project_response.slug,
            "environment": project_response.environment,
            "rate_limits": {
                "requests_per_minute": request.state.rate_limits["per_minute"],
                "requests_per_hour": request.state.rate_limits["per_hour"],
            },
            "quotas": {
                "daily_quota": project_response.daily_quota,
                "daily_usage": usage_response.log_count,
                "quota_remaining": max(0, quota_remaining),
                "quota_reset_at": tomorrow.isoformat(),
            },
            "constraints": {
                "max_batch_size": 1000,
                "max_message_length": 10000,
                "max_error_message_length": 5000,
                "max_stack_trace_length": 50000,
                "max_attributes_size_bytes": 102400,
                "max_environment_length": 20,
                "max_release_length": 100,
                "max_sdk_version_length": 20,
                "max_platform_length": 50,
                "max_platform_version_length": 50,
                "max_error_type_length": 255,
                "supported_log_levels": ["debug", "info", "warning", "error", "critical"],
                "supported_log_types": ["console", "logger", "exception", "custom"],
                "supported_importance_levels": ["low", "standard", "high"],
            },
            "features": {
                "batch_ingestion": True,
                "compression": False,
                "streaming": False,
                "endpoint_monitoring": True,
            },
            "server_info": {
                "version": "1.0.0",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        }

    except grpc.RpcError as e:
        logger.error(f"gRPC error fetching settings: {e.code()} - {e.details()}")
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise fastapi.HTTPException(
                status_code=404,
                detail="Project not found",
            )
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to fetch settings",
        )

    except Exception as e:
        logger.error(f"Failed to fetch settings: {e}", exc_info=True)
        raise fastapi.HTTPException(
            status_code=500,
            detail="Failed to fetch settings",
        )
