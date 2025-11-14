import grpc
from auth_service import database
from auth_service.proto import auth_pb2, auth_pb2_grpc
from auth_service.services import auth_service, dashboard_service
from redis.asyncio import Redis


class AuthServicer(auth_pb2_grpc.AuthServiceServicer):
    """Implements all Auth Service RPC methods."""

    def __init__(self, redis: Redis):
        self.auth_service = auth_service.AuthService(redis)
        self.dashboard_service = dashboard_service.DashboardService(redis)

    # ==================== Account Operations ====================

    async def Register(
        self,
        request: auth_pb2.RegisterRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RegisterResponse:
        """Register new account."""
        try:
            async with database.get_session() as session:
                account = await self.auth_service.register(
                    session=session,
                    email=request.email,
                    password=request.password,
                    name=request.email.split("@")[0],
                    plan=request.plan or "free",
                )

                return auth_pb2.RegisterResponse(
                    account_id=account.id,
                    email=account.email,
                    plan=account.plan,
                    name=account.name,
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.RegisterResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.RegisterResponse()

    async def Login(
        self,
        request: auth_pb2.LoginRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LoginResponse:
        """Login and return account info."""
        try:
            async with database.get_session() as session:
                account = await self.auth_service.login(
                    session=session,
                    email=request.email,
                    password=request.password,
                )

                access_token = f"token_{account.id}_{account.email}"

                return auth_pb2.LoginResponse(
                    account_id=account.id,
                    email=account.email,
                    plan=account.plan,
                    access_token=access_token,
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details(str(e))
            return auth_pb2.LoginResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.LoginResponse()

    async def GetAccount(
        self,
        request: auth_pb2.GetAccountRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetAccountResponse:
        """Get account by ID."""
        try:
            async with database.get_session() as session:
                account = await self.auth_service.get_account_by_id(
                    session=session,
                    account_id=request.account_id,
                )

                if not account:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Account not found")
                    return auth_pb2.GetAccountResponse()

                return auth_pb2.GetAccountResponse(
                    account_id=account.id,
                    email=account.email,
                    plan=account.plan,
                    status=account.status,
                    name=account.name,
                    created_at=account.created_at.isoformat(),
                )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetAccountResponse()

    # ==================== Project Operations ====================

    async def CreateProject(
        self,
        request: auth_pb2.CreateProjectRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.CreateProjectResponse:
        """Create new project."""
        try:
            async with database.get_session() as session:
                project = await self.auth_service.create_project(
                    session=session,
                    account_id=request.account_id,
                    name=request.name,
                    slug=request.slug,
                    environment=request.environment or "production",
                )

                return auth_pb2.CreateProjectResponse(
                    project_id=project.id,
                    name=project.name,
                    slug=project.slug,
                    environment=project.environment,
                    retention_days=project.retention_days,
                    daily_quota=project.daily_quota,
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.CreateProjectResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.CreateProjectResponse()

    async def GetProjects(
        self,
        request: auth_pb2.GetProjectsRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetProjectsResponse:
        """Get all projects for account."""
        try:
            async with database.get_session() as session:
                projects = await self.auth_service.get_projects_for_account(
                    session=session,
                    account_id=request.account_id,
                )

                project_infos = [
                    auth_pb2.ProjectInfo(
                        project_id=p.id,
                        name=p.name,
                        slug=p.slug,
                        environment=p.environment,
                        retention_days=p.retention_days,
                        daily_quota=p.daily_quota,
                    )
                    for p in projects
                ]

                return auth_pb2.GetProjectsResponse(projects=project_infos)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetProjectsResponse()

    async def GetProjectById(
        self,
        request: auth_pb2.GetProjectByIdRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetProjectByIdResponse:
        """Get project by ID."""
        try:
            async with database.get_session() as session:
                project = await self.auth_service.get_project_by_id(
                    session=session,
                    project_id=request.project_id,
                )

                if not project:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Project not found")
                    return auth_pb2.GetProjectByIdResponse()

                return auth_pb2.GetProjectByIdResponse(
                    project_id=project.id,
                    name=project.name,
                    slug=project.slug,
                    environment=project.environment,
                    retention_days=project.retention_days,
                    daily_quota=project.daily_quota,
                )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetProjectByIdResponse()

    # ==================== API Key Operations ====================

    async def CreateApiKey(
        self,
        request: auth_pb2.CreateApiKeyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.CreateApiKeyResponse:
        """Create API key."""
        try:
            async with database.get_session() as session:
                full_key, api_key = await self.auth_service.create_api_key(
                    session=session,
                    project_id=request.project_id,
                    name=request.name or None,
                )

                return auth_pb2.CreateApiKeyResponse(
                    key_id=api_key.id,
                    full_key=full_key,
                    key_prefix=api_key.key_prefix,
                )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.CreateApiKeyResponse()

    async def ValidateApiKey(
        self,
        request: auth_pb2.ValidateApiKeyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ValidateApiKeyResponse:
        """
        Validate API key (CRITICAL PATH - called on every log ingestion).

        Performance: <5ms cached, <100ms uncached
        """
        try:
            async with database.get_session() as session:
                is_valid, project_id, info = await self.auth_service.validate_api_key(
                    session=session,
                    api_key=request.api_key,
                )

                if not is_valid:
                    return auth_pb2.ValidateApiKeyResponse(
                        valid=False,
                        error_message=info.get("error", "Invalid API key"),
                    )

                return auth_pb2.ValidateApiKeyResponse(
                    valid=True,
                    project_id=project_id,
                    account_id=info.get("account_id", 0),
                    daily_quota=info["daily_quota"],
                    retention_days=info["retention_days"],
                    rate_limit_per_minute=info["rate_limit_per_minute"],
                    rate_limit_per_hour=info["rate_limit_per_hour"],
                    current_usage=info.get("current_usage", 0),
                )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ValidateApiKeyResponse(valid=False)

    async def RevokeApiKey(
        self,
        request: auth_pb2.RevokeApiKeyRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RevokeApiKeyResponse:
        """Revoke API key."""
        try:
            async with database.get_session() as session:
                await self.auth_service.revoke_api_key(
                    session=session,
                    key_id=request.key_id,
                )

                return auth_pb2.RevokeApiKeyResponse(success=True)

        except ValueError as e:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return auth_pb2.RevokeApiKeyResponse(success=False)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.RevokeApiKeyResponse(success=False)

    # ==================== Usage Tracking Operations ====================

    async def GetDailyUsage(
        self,
        request: auth_pb2.GetDailyUsageRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetDailyUsageResponse:
        """Get daily usage statistics for a project."""
        try:
            async with database.get_session() as session:
                usage = await self.auth_service.get_daily_usage(
                    session=session,
                    project_id=request.project_id,
                    date=request.date,
                )

                if not usage:
                    return auth_pb2.GetDailyUsageResponse(
                        log_count=0,
                        date=request.date,
                    )

                return auth_pb2.GetDailyUsageResponse(
                    log_count=usage.logs_ingested,
                    date=request.date,
                )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetDailyUsageResponse(log_count=0, date=request.date)

    # ==================== Dashboard Panel Operations ====================

    async def GetDashboardPanels(
        self,
        request: auth_pb2.GetDashboardPanelsRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetDashboardPanelsResponse:
        """Get all dashboard panels for a user."""
        try:
            async with database.get_session() as session:
                panels = await self.dashboard_service.get_dashboard_panels(
                    session=session,
                    user_id=request.user_id,
                )

                panel_messages = [
                    auth_pb2.Panel(
                        id=panel["id"],
                        name=panel["name"],
                        index=panel["index"],
                        project_id=panel["project_id"],
                        time_range_from=panel["time_range_from"],
                        time_range_to=panel["time_range_to"],
                        type=panel["type"],
                    )
                    for panel in panels
                ]

                return auth_pb2.GetDashboardPanelsResponse(panels=panel_messages)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetDashboardPanelsResponse()

    async def CreateDashboardPanel(
        self,
        request: auth_pb2.CreateDashboardPanelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.CreateDashboardPanelResponse:
        """Create a new dashboard panel."""
        try:
            async with database.get_session() as session:
                panel = await self.dashboard_service.create_dashboard_panel(
                    session=session,
                    user_id=request.user_id,
                    name=request.name,
                    index=request.index,
                    project_id=request.project_id,
                    time_range_from=request.time_range_from,
                    time_range_to=request.time_range_to,
                    panel_type=request.type,
                )

                panel_message = auth_pb2.Panel(
                    id=panel["id"],
                    name=panel["name"],
                    index=panel["index"],
                    project_id=panel["project_id"],
                    time_range_from=panel["time_range_from"],
                    time_range_to=panel["time_range_to"],
                    type=panel["type"],
                )

                return auth_pb2.CreateDashboardPanelResponse(panel=panel_message)

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.CreateDashboardPanelResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.CreateDashboardPanelResponse()

    async def UpdateDashboardPanel(
        self,
        request: auth_pb2.UpdateDashboardPanelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UpdateDashboardPanelResponse:
        """Update an existing dashboard panel."""
        try:
            async with database.get_session() as session:
                panel = await self.dashboard_service.update_dashboard_panel(
                    session=session,
                    user_id=request.user_id,
                    panel_id=request.panel_id,
                    name=request.name,
                    index=request.index,
                    project_id=request.project_id,
                    time_range_from=request.time_range_from,
                    time_range_to=request.time_range_to,
                    panel_type=request.type,
                )

                panel_message = auth_pb2.Panel(
                    id=panel["id"],
                    name=panel["name"],
                    index=panel["index"],
                    project_id=panel["project_id"],
                    time_range_from=panel["time_range_from"],
                    time_range_to=panel["time_range_to"],
                    type=panel["type"],
                )

                return auth_pb2.UpdateDashboardPanelResponse(panel=panel_message)

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.UpdateDashboardPanelResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.UpdateDashboardPanelResponse()

    async def DeleteDashboardPanel(
        self,
        request: auth_pb2.DeleteDashboardPanelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.DeleteDashboardPanelResponse:
        """Delete a dashboard panel."""
        try:
            async with database.get_session() as session:
                success = await self.dashboard_service.delete_dashboard_panel(
                    session=session,
                    user_id=request.user_id,
                    panel_id=request.panel_id,
                )

                return auth_pb2.DeleteDashboardPanelResponse(success=success)

        except ValueError as e:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(str(e))
            return auth_pb2.DeleteDashboardPanelResponse(success=False)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.DeleteDashboardPanelResponse(success=False)
