import datetime
import typing

import pydantic


class ErrorGroupResponse(pydantic.BaseModel):
    id: int = pydantic.Field(description="Error group ID")
    project_id: int = pydantic.Field(description="Project ID")
    fingerprint: str = pydantic.Field(description="Error fingerprint (grouping key)")
    error_type: str = pydantic.Field(description="Error type (e.g., ValueError)")
    error_message: typing.Optional[str] = pydantic.Field(default=None, description="Error message")
    first_seen: datetime.datetime = pydantic.Field(description="First occurrence timestamp")
    last_seen: datetime.datetime = pydantic.Field(description="Most recent occurrence timestamp")
    occurrence_count: int = pydantic.Field(description="Total occurrence count")
    status: typing.Literal["unresolved", "resolved", "ignored", "muted"] = pydantic.Field(
        description="Workflow status"
    )
    assigned_to: typing.Optional[int] = pydantic.Field(
        default=None, description="Account ID assigned to this error group"
    )
    sample_log_id: typing.Optional[int] = pydantic.Field(
        default=None, description="Sample log entry ID"
    )
    resolved_at: typing.Optional[datetime.datetime] = pydantic.Field(
        default=None, description="When this group was last resolved"
    )
    resolved_in_release: typing.Optional[str] = pydantic.Field(
        default=None, description="Release the fix was resolved in"
    )


class ErrorGroupListResponse(pydantic.BaseModel):
    project_id: int = pydantic.Field(description="Project ID")
    groups: list[ErrorGroupResponse] = pydantic.Field(description="List of error groups")
    total: int = pydantic.Field(description="Total number of error groups matching filters")
    has_more: bool = pydantic.Field(description="Whether there are more error groups to fetch")


class ErrorOccurrenceBucket(pydantic.BaseModel):
    bucket: datetime.datetime = pydantic.Field(description="Hour bucket start")
    count: int = pydantic.Field(description="Occurrence count in this bucket")


class ErrorGroupDetailResponse(pydantic.BaseModel):
    group: ErrorGroupResponse = pydantic.Field(description="Error group")
    sample_stack_trace: typing.Optional[str] = pydantic.Field(
        default=None, description="Sample stack trace"
    )
    sample_log: typing.Optional[dict] = pydantic.Field(
        default=None, description="Full sample log entry"
    )
    occurrence_sparkline: list[ErrorOccurrenceBucket] = pydantic.Field(
        default_factory=list,
        description="Hourly occurrence counts over the last 24 hours",
    )


class UpdateErrorGroupStatusRequest(pydantic.BaseModel):
    status: typing.Literal["unresolved", "resolved", "ignored", "muted"] = pydantic.Field(
        description="New workflow status"
    )
    resolved_in_release: typing.Optional[str] = pydantic.Field(
        default=None,
        description="Release the fix shipped in (only applied when status is 'resolved')",
        max_length=100,
    )


class AssignErrorGroupRequest(pydantic.BaseModel):
    assigned_to: typing.Optional[int] = pydantic.Field(
        default=None, description="Account ID to assign this error group to, or null to unassign"
    )
