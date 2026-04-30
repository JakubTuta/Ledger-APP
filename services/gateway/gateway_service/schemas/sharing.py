import pydantic


class GenerateInviteCodeResponse(pydantic.BaseModel):
    code: str = pydantic.Field(..., description="Invite code (format: XXXX-XXXX-XXXX). Valid for 1 hour.")
    expires_at: str = pydantic.Field(..., description="Expiration time (ISO 8601)")


class AcceptInviteCodeRequest(pydantic.BaseModel):
    code: str = pydantic.Field(..., min_length=1, description="Invite code (with or without dashes)")


class AcceptInviteCodeResponse(pydantic.BaseModel):
    project_id: int
    role: str
    project_name: str
    project_slug: str


class MemberInfo(pydantic.BaseModel):
    account_id: int
    email: str
    name: str
    role: str
    joined_at: str


class ListMembersResponse(pydantic.BaseModel):
    members: list[MemberInfo]
    total: int


class RemoveMemberResponse(pydantic.BaseModel):
    success: bool
    message: str


class LeaveProjectResponse(pydantic.BaseModel):
    success: bool
    message: str
