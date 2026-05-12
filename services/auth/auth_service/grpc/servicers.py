import json

import grpc
import sqlalchemy as sa
from auth_service import config, database
from auth_service import models
from auth_service.proto import auth_pb2, auth_pb2_grpc
from auth_service.services import auth_service, dashboard_service
from auth_service.utils import jwt_utils
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
        """Login and return JWT access token + refresh token."""
        try:
            async with database.get_session() as session:
                account = await self.auth_service.login(
                    session=session,
                    email=request.email,
                    password=request.password,
                )

                access_token = jwt_utils.create_access_token(
                    account_id=account.id,
                    email=account.email,
                )

                refresh_token, _ = await self.auth_service.create_refresh_token(
                    session=session,
                    account_id=account.id,
                    device_info=None,
                )

                settings = config.get_settings()
                expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

                return auth_pb2.LoginResponse(
                    account_id=account.id,
                    email=account.email,
                    plan=account.plan,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_in=expires_in,
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.UNAUTHENTICATED)
            context.set_details(str(e))
            return auth_pb2.LoginResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.LoginResponse()

    async def RefreshToken(
        self,
        request: auth_pb2.RefreshTokenRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RefreshTokenResponse:
        """Refresh access token using refresh token."""
        try:
            async with database.get_session() as session:
                account = await self.auth_service.validate_refresh_token(
                    session=session,
                    raw_token=request.refresh_token,
                )

                if not account:
                    context.set_code(grpc.StatusCode.UNAUTHENTICATED)
                    context.set_details("Invalid or expired refresh token")
                    return auth_pb2.RefreshTokenResponse()

                new_access_token = jwt_utils.create_access_token(
                    account_id=account.id,
                    email=account.email,
                )

                new_refresh_token, _ = await self.auth_service.create_refresh_token(
                    session=session,
                    account_id=account.id,
                    device_info=None,
                )

                await self.auth_service.revoke_refresh_token(
                    session=session,
                    raw_token=request.refresh_token,
                )

                settings = config.get_settings()
                expires_in = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60

                return auth_pb2.RefreshTokenResponse(
                    access_token=new_access_token,
                    refresh_token=new_refresh_token,
                    expires_in=expires_in,
                    account_id=account.id,
                    email=account.email,
                )

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.RefreshTokenResponse()

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

    async def UpdateAccountName(
        self,
        request: auth_pb2.UpdateAccountNameRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UpdateAccountNameResponse:
        """Update account name."""
        try:
            async with database.get_session() as session:
                account = await self.auth_service.update_account_name(
                    session=session,
                    account_id=request.account_id,
                    name=request.name,
                )

                return auth_pb2.UpdateAccountNameResponse(
                    success=True,
                    name=account.name,
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.UpdateAccountNameResponse(success=False)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.UpdateAccountNameResponse(success=False)

    async def ChangePassword(
        self,
        request: auth_pb2.ChangePasswordRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ChangePasswordResponse:
        """Change account password."""
        try:
            async with database.get_session() as session:
                await self.auth_service.change_password(
                    session=session,
                    account_id=request.account_id,
                    old_password=request.old_password,
                    new_password=request.new_password,
                )

                return auth_pb2.ChangePasswordResponse(success=True)

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.ChangePasswordResponse(success=False)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ChangePasswordResponse(success=False)

    async def GetNotificationPreferences(
        self,
        request: auth_pb2.GetNotificationPreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetNotificationPreferencesResponse:
        """Get notification preferences for account."""
        try:
            async with database.get_session() as session:
                preferences = await self.auth_service.get_notification_preferences(
                    session=session,
                    account_id=request.account_id,
                )

                proto_preferences = self._convert_to_proto_preferences(preferences)

                return auth_pb2.GetNotificationPreferencesResponse(
                    preferences=proto_preferences
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.GetNotificationPreferencesResponse()

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetNotificationPreferencesResponse()

    async def UpdateNotificationPreferences(
        self,
        request: auth_pb2.UpdateNotificationPreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UpdateNotificationPreferencesResponse:
        """Update notification preferences for account."""
        try:
            async with database.get_session() as session:
                preferences_dict = self._convert_from_proto_preferences(
                    request.preferences
                )

                updated_preferences = await self.auth_service.update_notification_preferences(
                    session=session,
                    account_id=request.account_id,
                    preferences=preferences_dict,
                )

                proto_preferences = self._convert_to_proto_preferences(
                    updated_preferences
                )

                return auth_pb2.UpdateNotificationPreferencesResponse(
                    success=True, preferences=proto_preferences
                )

        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.UpdateNotificationPreferencesResponse(success=False)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.UpdateNotificationPreferencesResponse(success=False)

    def _convert_to_proto_preferences(
        self, preferences: dict
    ) -> auth_pb2.NotificationPreferences:
        """Convert dict preferences to protobuf NotificationPreferences."""
        projects_map = {}
        for project_id_str, settings in preferences.get("projects", {}).items():
            project_id = int(project_id_str)
            projects_map[project_id] = auth_pb2.ProjectNotificationSettings(
                enabled=settings.get("enabled", True),
                levels=settings.get("levels", []),
                types=settings.get("types", []),
            )

        return auth_pb2.NotificationPreferences(
            enabled=preferences.get("enabled", True), projects=projects_map
        )

    def _convert_from_proto_preferences(
        self, proto_preferences: auth_pb2.NotificationPreferences
    ) -> dict:
        """Convert protobuf NotificationPreferences to dict."""
        projects = {}
        for project_id, settings in proto_preferences.projects.items():
            projects[str(project_id)] = {
                "enabled": settings.enabled,
                "levels": list(settings.levels),
                "types": list(settings.types),
            }

        return {"enabled": proto_preferences.enabled, "projects": projects}

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

                for flag_key in ("tracing", "custom_metrics", "alert_rules"):
                    session.add(
                        models.FeatureFlag(
                            project_id=project.id,
                            key=flag_key,
                            enabled=True,
                        )
                    )
                await session.flush()

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
                        available_routes=p.available_routes or [],
                        role=role,
                    )
                    for p, role in projects
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
                    available_routes=project.available_routes or [],
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

        except ValueError as e:
            context.set_code(grpc.StatusCode.ALREADY_EXISTS)
            context.set_details(str(e))
            return auth_pb2.CreateApiKeyResponse()

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

    async def ListApiKeys(
        self,
        request: auth_pb2.ListApiKeysRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ListApiKeysResponse:
        """List all API keys for a project."""
        try:
            async with database.get_session() as session:
                api_keys = await self.auth_service.list_api_keys(
                    session=session,
                    project_id=request.project_id,
                )

                api_key_infos = []
                for api_key in api_keys:
                    api_key_infos.append(
                        auth_pb2.ApiKeyInfo(
                            key_id=api_key.id,
                            project_id=api_key.project_id,
                            name=api_key.name or "",
                            key_prefix=api_key.key_prefix,
                            status=api_key.status,
                            created_at=api_key.created_at.isoformat(),
                            last_used_at=api_key.last_used_at.isoformat()
                            if api_key.last_used_at
                            else "",
                        )
                    )

                return auth_pb2.ListApiKeysResponse(api_keys=api_key_infos)

        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ListApiKeysResponse()

    # ==================== Project Sharing Operations ====================

    async def GenerateInviteCode(
        self,
        request: auth_pb2.GenerateInviteCodeRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GenerateInviteCodeResponse:
        """Generate invite code for a project (owner only)."""
        try:
            async with database.get_session() as session:
                code, expires_at = await self.auth_service.generate_invite_code(
                    session=session,
                    project_id=request.project_id,
                    requester_account_id=request.requester_account_id,
                )
                return auth_pb2.GenerateInviteCodeResponse(
                    code=code,
                    expires_at=expires_at.isoformat(),
                )
        except PermissionError as e:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(str(e))
            return auth_pb2.GenerateInviteCodeResponse()
        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.GenerateInviteCodeResponse()
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GenerateInviteCodeResponse()

    async def AcceptInviteCode(
        self,
        request: auth_pb2.AcceptInviteCodeRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.AcceptInviteCodeResponse:
        """Accept invite code and join project as member."""
        try:
            async with database.get_session() as session:
                project = await self.auth_service.accept_invite_code(
                    session=session,
                    code=request.code,
                    account_id=request.account_id,
                )
                return auth_pb2.AcceptInviteCodeResponse(
                    project_id=project.id,
                    role="member",
                    project_name=project.name,
                    project_slug=project.slug,
                )
        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.AcceptInviteCodeResponse()
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.AcceptInviteCodeResponse()

    async def ListProjectMembers(
        self,
        request: auth_pb2.ListProjectMembersRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ListProjectMembersResponse:
        """List all members of a project."""
        try:
            async with database.get_session() as session:
                members = await self.auth_service.list_project_members(
                    session=session,
                    project_id=request.project_id,
                    requester_account_id=request.requester_account_id,
                )
                member_infos = [
                    auth_pb2.MemberInfo(
                        account_id=m["account_id"],
                        email=m["email"],
                        name=m["name"],
                        role=m["role"],
                        joined_at=m["joined_at"],
                    )
                    for m in members
                ]
                return auth_pb2.ListProjectMembersResponse(members=member_infos)
        except PermissionError as e:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(str(e))
            return auth_pb2.ListProjectMembersResponse()
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ListProjectMembersResponse()

    async def RemoveProjectMember(
        self,
        request: auth_pb2.RemoveProjectMemberRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.RemoveProjectMemberResponse:
        """Remove a member from a project (owner only)."""
        try:
            async with database.get_session() as session:
                await self.auth_service.remove_project_member(
                    session=session,
                    project_id=request.project_id,
                    account_id=request.account_id,
                    requester_account_id=request.requester_account_id,
                )
                return auth_pb2.RemoveProjectMemberResponse(success=True)
        except PermissionError as e:
            context.set_code(grpc.StatusCode.PERMISSION_DENIED)
            context.set_details(str(e))
            return auth_pb2.RemoveProjectMemberResponse(success=False)
        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.RemoveProjectMemberResponse(success=False)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.RemoveProjectMemberResponse(success=False)

    async def LeaveProject(
        self,
        request: auth_pb2.LeaveProjectRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.LeaveProjectResponse:
        """Leave a project."""
        try:
            async with database.get_session() as session:
                await self.auth_service.leave_project(
                    session=session,
                    project_id=request.project_id,
                    account_id=request.account_id,
                )
                return auth_pb2.LeaveProjectResponse(success=True)
        except ValueError as e:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return auth_pb2.LeaveProjectResponse(success=False)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.LeaveProjectResponse(success=False)

    async def GetProjectRole(
        self,
        request: auth_pb2.GetProjectRoleRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetProjectRoleResponse:
        """Get a user's role in a project."""
        try:
            async with database.get_session() as session:
                role = await self.auth_service.get_project_role(
                    session=session,
                    project_id=request.project_id,
                    account_id=request.account_id,
                )
                if role is None:
                    return auth_pb2.GetProjectRoleResponse(is_member=False, role="")
                return auth_pb2.GetProjectRoleResponse(is_member=True, role=role)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetProjectRoleResponse(is_member=False, role="")

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
                        period=panel.get("period"),
                        periodFrom=panel.get("periodFrom"),
                        periodTo=panel.get("periodTo"),
                        type=panel["type"],
                        endpoint=panel.get("endpoint", ""),
                        routes=panel.get("routes", []),
                        statistic=panel.get("statistic", ""),
                        layout=auth_pb2.PanelLayout(**panel["layout"]) if panel.get("layout") else None,
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
                req_layout = None
                if request.HasField("layout"):
                    req_layout = {"x": request.layout.x, "y": request.layout.y, "w": request.layout.w, "h": request.layout.h}

                panel = await self.dashboard_service.create_dashboard_panel(
                    session=session,
                    user_id=request.user_id,
                    name=request.name,
                    index=request.index,
                    project_id=request.project_id,
                    panel_type=request.type,
                    period=request.period if request.HasField("period") else None,
                    period_from=request.periodFrom if request.HasField("periodFrom") else None,
                    period_to=request.periodTo if request.HasField("periodTo") else None,
                    endpoint=request.endpoint if request.endpoint else None,
                    routes=list(request.routes) if request.routes else None,
                    statistic=request.statistic if request.statistic else None,
                    layout=req_layout,
                )

                panel_message = auth_pb2.Panel(
                    id=panel["id"],
                    name=panel["name"],
                    index=panel["index"],
                    project_id=panel["project_id"],
                    period=panel.get("period"),
                    periodFrom=panel.get("periodFrom"),
                    periodTo=panel.get("periodTo"),
                    type=panel["type"],
                    endpoint=panel.get("endpoint", ""),
                    routes=panel.get("routes", []),
                    statistic=panel.get("statistic", ""),
                    layout=auth_pb2.PanelLayout(**panel["layout"]) if panel.get("layout") else None,
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
                req_layout = None
                if request.HasField("layout"):
                    req_layout = {"x": request.layout.x, "y": request.layout.y, "w": request.layout.w, "h": request.layout.h}

                panel = await self.dashboard_service.update_dashboard_panel(
                    session=session,
                    user_id=request.user_id,
                    panel_id=request.panel_id,
                    name=request.name,
                    index=request.index,
                    project_id=request.project_id,
                    panel_type=request.type,
                    period=request.period if request.HasField("period") else None,
                    period_from=request.periodFrom if request.HasField("periodFrom") else None,
                    period_to=request.periodTo if request.HasField("periodTo") else None,
                    endpoint=request.endpoint if request.endpoint else None,
                    routes=list(request.routes) if request.routes else None,
                    statistic=request.statistic if request.statistic else None,
                    layout=req_layout,
                )

                panel_message = auth_pb2.Panel(
                    id=panel["id"],
                    name=panel["name"],
                    index=panel["index"],
                    project_id=panel["project_id"],
                    period=panel.get("period"),
                    periodFrom=panel.get("periodFrom"),
                    periodTo=panel.get("periodTo"),
                    type=panel["type"],
                    endpoint=panel.get("endpoint", ""),
                    routes=panel.get("routes", []),
                    statistic=panel.get("statistic", ""),
                    layout=auth_pb2.PanelLayout(**panel["layout"]) if panel.get("layout") else None,
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

    # ==================== Feature Flag Operations ====================

    async def GetFeatureFlags(
        self,
        request: auth_pb2.GetFeatureFlagsRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetFeatureFlagsResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.FeatureFlag).where(
                        models.FeatureFlag.project_id == request.project_id
                    )
                )
                rows = result.scalars().all()
                flags = [
                    auth_pb2.FeatureFlag(key=r.key, enabled=r.enabled) for r in rows
                ]
                return auth_pb2.GetFeatureFlagsResponse(flags=flags)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetFeatureFlagsResponse()

    async def SetFeatureFlag(
        self,
        request: auth_pb2.SetFeatureFlagRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.SetFeatureFlagResponse:
        try:
            async with database.get_session() as session:
                await session.execute(
                    sa.text("""
                        INSERT INTO feature_flags (project_id, key, enabled, created_at, updated_at)
                        VALUES (:project_id, :key, :enabled, NOW(), NOW())
                        ON CONFLICT (project_id, key) DO UPDATE
                        SET enabled = EXCLUDED.enabled, updated_at = NOW()
                    """),
                    {
                        "project_id": request.project_id,
                        "key": request.key,
                        "enabled": request.enabled,
                    },
                )
                await session.commit()
                return auth_pb2.SetFeatureFlagResponse(
                    success=True,
                    flag=auth_pb2.FeatureFlag(key=request.key, enabled=request.enabled),
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.SetFeatureFlagResponse(success=False)

    # ==================== Notification Inbox Operations ====================

    async def ListNotifications(
        self,
        request: auth_pb2.ListNotificationsRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ListNotificationsResponse:
        try:
            async with database.get_session() as session:
                limit = request.limit if request.HasField("limit") else 50
                query = sa.select(models.Notification).where(
                    models.Notification.user_id == request.user_id
                )
                if request.HasField("unread_only") and request.unread_only:
                    query = query.where(models.Notification.read_at == None)  # noqa: E711
                if request.HasField("before_id"):
                    query = query.where(models.Notification.id < request.before_id)
                query = query.order_by(models.Notification.id.desc()).limit(limit + 1)
                result = await session.execute(query)
                rows = result.scalars().all()
                has_more = len(rows) > limit
                rows = rows[:limit]
                items = [_notification_to_proto(n) for n in rows]
                return auth_pb2.ListNotificationsResponse(
                    notifications=items, has_more=has_more
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ListNotificationsResponse()

    async def GetUnreadNotificationCount(
        self,
        request: auth_pb2.GetUnreadNotificationCountRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetUnreadNotificationCountResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(sa.func.count(models.Notification.id)).where(
                        models.Notification.user_id == request.user_id,
                        models.Notification.read_at == None,  # noqa: E711
                    )
                )
                count = result.scalar() or 0
                return auth_pb2.GetUnreadNotificationCountResponse(count=count)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetUnreadNotificationCountResponse(count=0)

    async def MarkNotificationRead(
        self,
        request: auth_pb2.MarkNotificationReadRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MarkNotificationReadResponse:
        try:
            async with database.get_session() as session:
                await session.execute(
                    sa.update(models.Notification)
                    .where(
                        models.Notification.id == request.notification_id,
                        models.Notification.user_id == request.user_id,
                        models.Notification.read_at == None,  # noqa: E711
                    )
                    .values(read_at=sa.func.now())
                )
                await session.commit()
                return auth_pb2.MarkNotificationReadResponse(success=True)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.MarkNotificationReadResponse(success=False)

    async def MarkAllNotificationsRead(
        self,
        request: auth_pb2.MarkAllNotificationsReadRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.MarkAllNotificationsReadResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.update(models.Notification)
                    .where(
                        models.Notification.user_id == request.user_id,
                        models.Notification.read_at == None,  # noqa: E711
                    )
                    .values(read_at=sa.func.now())
                )
                await session.commit()
                return auth_pb2.MarkAllNotificationsReadResponse(
                    updated_count=result.rowcount
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.MarkAllNotificationsReadResponse(updated_count=0)

    async def DeleteNotification(
        self,
        request: auth_pb2.DeleteNotificationRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.DeleteNotificationResponse:
        try:
            async with database.get_session() as session:
                await session.execute(
                    sa.delete(models.Notification).where(
                        models.Notification.id == request.notification_id,
                        models.Notification.user_id == request.user_id,
                    )
                )
                await session.commit()
                return auth_pb2.DeleteNotificationResponse(success=True)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.DeleteNotificationResponse(success=False)

    async def CreateNotification(
        self,
        request: auth_pb2.CreateNotificationRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.CreateNotificationResponse:
        try:
            async with database.get_session() as session:
                severity_map = {0: "info", 1: "warning", 2: "critical"}
                severity_str = severity_map.get(request.severity, "info")
                payload = json.loads(request.payload) if request.payload else {}
                notif = models.Notification(
                    user_id=request.user_id,
                    project_id=request.project_id,
                    kind=request.kind,
                    severity=severity_str,
                    payload=payload,
                )
                session.add(notif)
                await session.commit()
                await session.refresh(notif)
                return auth_pb2.CreateNotificationResponse(
                    notification=_notification_to_proto(notif)
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.CreateNotificationResponse()

    # ==================== Alert Rule Operations ====================

    async def ListAlertRules(
        self,
        request: auth_pb2.ListAlertRulesRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ListAlertRulesResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertRule).where(
                        models.AlertRule.project_id == request.project_id
                    )
                )
                rules = result.scalars().all()
                return auth_pb2.ListAlertRulesResponse(
                    rules=[_alert_rule_to_proto(r) for r in rules]
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ListAlertRulesResponse()

    async def GetAlertRule(
        self,
        request: auth_pb2.GetAlertRuleRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetAlertRuleResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertRule).where(
                        models.AlertRule.id == request.rule_id,
                        models.AlertRule.project_id == request.project_id,
                    )
                )
                rule = result.scalar_one_or_none()
                if not rule:
                    return auth_pb2.GetAlertRuleResponse(found=False)
                return auth_pb2.GetAlertRuleResponse(
                    rule=_alert_rule_to_proto(rule), found=True
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetAlertRuleResponse(found=False)

    async def CreateAlertRule(
        self,
        request: auth_pb2.CreateAlertRuleRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.CreateAlertRuleResponse:
        try:
            async with database.get_session() as session:
                severity_map = {0: "info", 1: "warning", 2: "critical"}
                rule = models.AlertRule(
                    project_id=request.project_id,
                    name=request.name,
                    metric_type=request.metric,
                    comparator=request.comparator,
                    threshold=request.threshold,
                    window_minutes=max(1, request.window_seconds // 60),
                    cooldown_minutes=max(1, request.cooldown_seconds // 60),
                    severity=severity_map.get(request.severity, "warning"),
                    enabled=True,
                    state="ok",
                )
                session.add(rule)
                await session.commit()
                await session.refresh(rule)
                return auth_pb2.CreateAlertRuleResponse(rule=_alert_rule_to_proto(rule))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.CreateAlertRuleResponse()

    async def UpdateAlertRule(
        self,
        request: auth_pb2.UpdateAlertRuleRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UpdateAlertRuleResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertRule).where(
                        models.AlertRule.id == request.rule_id,
                        models.AlertRule.project_id == request.project_id,
                    )
                )
                rule = result.scalar_one_or_none()
                if not rule:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Alert rule not found")
                    return auth_pb2.UpdateAlertRuleResponse()
                if request.HasField("name"):
                    rule.name = request.name
                if request.HasField("enabled"):
                    rule.enabled = request.enabled
                if request.HasField("threshold"):
                    rule.threshold = request.threshold
                if request.HasField("cooldown_seconds"):
                    rule.cooldown_minutes = max(1, request.cooldown_seconds // 60)
                await session.commit()
                await session.refresh(rule)
                return auth_pb2.UpdateAlertRuleResponse(rule=_alert_rule_to_proto(rule))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.UpdateAlertRuleResponse()

    async def DeleteAlertRule(
        self,
        request: auth_pb2.DeleteAlertRuleRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.DeleteAlertRuleResponse:
        try:
            async with database.get_session() as session:
                await session.execute(
                    sa.delete(models.AlertRule).where(
                        models.AlertRule.id == request.rule_id,
                        models.AlertRule.project_id == request.project_id,
                    )
                )
                await session.commit()
                return auth_pb2.DeleteAlertRuleResponse(success=True)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.DeleteAlertRuleResponse(success=False)

    # ==================== Alert Channel Operations ====================

    async def ListAlertChannels(
        self,
        request: auth_pb2.ListAlertChannelsRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.ListAlertChannelsResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertChannel, models.AlertRule.project_id)
                    .join(
                        models.AlertRule,
                        models.AlertChannel.rule_id == models.AlertRule.id,
                    )
                    .where(models.AlertRule.project_id == request.project_id)
                )
                rows = result.all()
                channels = [
                    _alert_channel_to_proto(ch, proj_id) for ch, proj_id in rows
                ]
                return auth_pb2.ListAlertChannelsResponse(channels=channels)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.ListAlertChannelsResponse()

    async def GetAlertChannel(
        self,
        request: auth_pb2.GetAlertChannelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetAlertChannelResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertChannel, models.AlertRule.project_id)
                    .join(
                        models.AlertRule,
                        models.AlertChannel.rule_id == models.AlertRule.id,
                    )
                    .where(
                        models.AlertChannel.id == request.channel_id,
                        models.AlertRule.project_id == request.project_id,
                    )
                )
                row = result.first()
                if not row:
                    return auth_pb2.GetAlertChannelResponse(found=False)
                ch, proj_id = row
                return auth_pb2.GetAlertChannelResponse(
                    channel=_alert_channel_to_proto(ch, proj_id), found=True
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetAlertChannelResponse(found=False)

    async def CreateAlertChannel(
        self,
        request: auth_pb2.CreateAlertChannelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.CreateAlertChannelResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertRule.id).where(
                        models.AlertRule.project_id == request.project_id
                    ).limit(1)
                )
                rule_id = result.scalar_one_or_none()
                if rule_id is None:
                    context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                    context.set_details("No alert rules exist for this project")
                    return auth_pb2.CreateAlertChannelResponse()
                config_dict = json.loads(request.config) if request.config else {}
                channel = models.AlertChannel(
                    rule_id=rule_id,
                    kind=request.kind,
                    config=config_dict,
                )
                session.add(channel)
                await session.commit()
                await session.refresh(channel)
                return auth_pb2.CreateAlertChannelResponse(
                    channel=_alert_channel_to_proto(channel, request.project_id)
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.CreateAlertChannelResponse()

    async def UpdateAlertChannel(
        self,
        request: auth_pb2.UpdateAlertChannelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UpdateAlertChannelResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.AlertChannel, models.AlertRule.project_id)
                    .join(
                        models.AlertRule,
                        models.AlertChannel.rule_id == models.AlertRule.id,
                    )
                    .where(
                        models.AlertChannel.id == request.channel_id,
                        models.AlertRule.project_id == request.project_id,
                    )
                )
                row = result.first()
                if not row:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details("Alert channel not found")
                    return auth_pb2.UpdateAlertChannelResponse()
                ch, proj_id = row
                if request.HasField("config"):
                    ch.config = json.loads(request.config)
                await session.commit()
                await session.refresh(ch)
                return auth_pb2.UpdateAlertChannelResponse(
                    channel=_alert_channel_to_proto(ch, proj_id)
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.UpdateAlertChannelResponse()

    async def DeleteAlertChannel(
        self,
        request: auth_pb2.DeleteAlertChannelRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.DeleteAlertChannelResponse:
        try:
            async with database.get_session() as session:
                subq = (
                    sa.select(models.AlertChannel.id)
                    .join(
                        models.AlertRule,
                        models.AlertChannel.rule_id == models.AlertRule.id,
                    )
                    .where(
                        models.AlertChannel.id == request.channel_id,
                        models.AlertRule.project_id == request.project_id,
                    )
                    .scalar_subquery()
                )
                await session.execute(
                    sa.delete(models.AlertChannel).where(
                        models.AlertChannel.id == subq
                    )
                )
                await session.commit()
                return auth_pb2.DeleteAlertChannelResponse(success=True)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.DeleteAlertChannelResponse(success=False)

    # ==================== Alert Notification Preference Operations ====================

    async def GetAlertNotificationPreferences(
        self,
        request: auth_pb2.GetAlertNotificationPreferencesRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.GetAlertNotificationPreferencesResponse:
        try:
            async with database.get_session() as session:
                result = await session.execute(
                    sa.select(models.NotificationPreference).where(
                        models.NotificationPreference.user_id == request.user_id,
                        models.NotificationPreference.project_id == request.project_id,
                    )
                )
                prefs = result.scalars().all()
                return auth_pb2.GetAlertNotificationPreferencesResponse(
                    preferences=[_notif_pref_to_proto(p) for p in prefs]
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.GetAlertNotificationPreferencesResponse()

    async def UpsertAlertNotificationPreference(
        self,
        request: auth_pb2.UpsertAlertNotificationPreferenceRequest,
        context: grpc.aio.ServicerContext,
    ) -> auth_pb2.UpsertAlertNotificationPreferenceResponse:
        try:
            async with database.get_session() as session:
                severity_map = {0: None, 1: "info", 2: "warning", 3: "critical"}
                severity_str = (
                    severity_map.get(request.severity)
                    if request.HasField("severity")
                    else None
                )
                rule_id = request.rule_id if request.HasField("rule_id") else None
                channels_dict = (
                    json.loads(request.channels)
                    if request.HasField("channels") and request.channels
                    else {}
                )
                delete_cond = (
                    models.NotificationPreference.user_id == request.user_id,
                    models.NotificationPreference.project_id == request.project_id,
                    (
                        models.NotificationPreference.rule_id == rule_id
                        if rule_id is not None
                        else models.NotificationPreference.rule_id == None  # noqa: E711
                    ),
                    (
                        models.NotificationPreference.severity == severity_str
                        if severity_str is not None
                        else models.NotificationPreference.severity == None  # noqa: E711
                    ),
                )
                await session.execute(
                    sa.delete(models.NotificationPreference).where(*delete_cond)
                )
                session.add(
                    models.NotificationPreference(
                        user_id=request.user_id,
                        project_id=request.project_id,
                        rule_id=rule_id,
                        severity=severity_str,
                        muted=request.muted,
                        channel_overrides=channels_dict,
                    )
                )
                await session.commit()
                rule_filter = (
                    models.NotificationPreference.rule_id == rule_id
                    if rule_id is not None
                    else models.NotificationPreference.rule_id.is_(None)
                )
                sev_filter = (
                    models.NotificationPreference.severity == severity_str
                    if severity_str is not None
                    else models.NotificationPreference.severity.is_(None)
                )
                result = await session.execute(
                    sa.select(models.NotificationPreference).where(
                        models.NotificationPreference.user_id == request.user_id,
                        models.NotificationPreference.project_id == request.project_id,
                        rule_filter,
                        sev_filter,
                    )
                )
                pref = result.scalar_one()
                return auth_pb2.UpsertAlertNotificationPreferenceResponse(
                    preference=_notif_pref_to_proto(pref)
                )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error: {str(e)}")
            return auth_pb2.UpsertAlertNotificationPreferenceResponse()


# ==================== Proto conversion helpers ====================

def _severity_str_to_int(s: str) -> int:
    return {"info": 0, "warning": 1, "critical": 2}.get(s, 0)


def _notification_to_proto(n: models.Notification) -> auth_pb2.NotificationItem:
    item = auth_pb2.NotificationItem(
        id=n.id,
        user_id=n.user_id,
        project_id=n.project_id,
        kind=n.kind,
        severity=_severity_str_to_int(n.severity),
        payload=json.dumps(n.payload) if n.payload else "{}",
        created_at=n.created_at.isoformat(),
        expires_at=n.expires_at.isoformat() if n.expires_at else "",
    )
    if n.read_at:
        item.read_at = n.read_at.isoformat()
    return item


def _alert_rule_to_proto(r: models.AlertRule) -> auth_pb2.AlertRule:
    rule = auth_pb2.AlertRule(
        id=r.id,
        project_id=r.project_id,
        name=r.name,
        enabled=r.enabled,
        metric=r.metric_type,
        tag_filter="{}",
        comparator=r.comparator,
        threshold=r.threshold,
        window_seconds=r.window_minutes * 60,
        cooldown_seconds=r.cooldown_minutes * 60,
        severity=_severity_str_to_int(r.severity),
        channels="[]",
        last_state=r.state,
        created_at=r.created_at.isoformat(),
        updated_at=r.updated_at.isoformat(),
    )
    if r.last_fired_at:
        rule.last_fired_at = r.last_fired_at.isoformat()
    return rule


def _alert_channel_to_proto(
    ch: models.AlertChannel, project_id: int
) -> auth_pb2.AlertChannel:
    config_safe = dict(ch.config or {})
    config_safe.pop("hmac_secret", None)
    return auth_pb2.AlertChannel(
        id=ch.id,
        project_id=project_id,
        user_id=0,
        kind=ch.kind,
        name=ch.kind,
        config=json.dumps(config_safe),
        enabled=True,
        created_at=ch.created_at.isoformat(),
    )


def _notif_pref_to_proto(
    p: models.NotificationPreference,
) -> auth_pb2.AlertNotificationPreference:
    pref = auth_pb2.AlertNotificationPreference(
        user_id=p.user_id,
        project_id=p.project_id,
        muted=p.muted,
        channels=json.dumps(p.channel_overrides) if p.channel_overrides else "[]",
    )
    if p.rule_id is not None:
        pref.rule_id = p.rule_id
    if p.severity is not None:
        pref.severity = _severity_str_to_int(p.severity)
    return pref
