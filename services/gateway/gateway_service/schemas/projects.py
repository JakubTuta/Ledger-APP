import typing

import pydantic


class CreateProjectRequest(pydantic.BaseModel):
    """Request body for creating a new project."""

    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Project display name",
        examples=["My Production App"],
    )
    slug: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9-]+$",
        description="Unique project identifier (lowercase, alphanumeric, hyphens only)",
        examples=["my-production-app"],
    )
    environment: str = pydantic.Field(
        default="production",
        pattern=r"^(production|staging|dev)$",
        description="Deployment environment (production, staging, or dev)",
        examples=["production"],
    )

    @pydantic.field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Slug must contain only alphanumeric characters, hyphens, and underscores"
            )

        return v.lower()

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "My Production App",
                    "slug": "my-production-app",
                    "environment": "production",
                }
            ]
        }
    )


class ProjectResponse(pydantic.BaseModel):
    """Project details response."""

    project_id: int = pydantic.Field(..., description="Unique project identifier")
    name: str = pydantic.Field(..., description="Project display name")
    slug: str = pydantic.Field(..., description="Project slug")
    environment: str = pydantic.Field(..., description="Deployment environment")
    retention_days: int = pydantic.Field(
        ..., description="Log retention period in days"
    )
    daily_quota: int = pydantic.Field(..., description="Daily log ingestion quota")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "name": "My Production App",
                    "slug": "my-production-app",
                    "environment": "production",
                    "retention_days": 30,
                    "daily_quota": 1000000,
                }
            ]
        }
    )


class ProjectListResponse(pydantic.BaseModel):
    """Response containing a list of projects."""

    projects: typing.List[ProjectResponse] = pydantic.Field(
        ..., description="List of projects"
    )
    total: int = pydantic.Field(..., description="Total number of projects")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "projects": [
                        {
                            "project_id": 456,
                            "name": "My Production App",
                            "slug": "my-production-app",
                            "environment": "production",
                            "retention_days": 30,
                            "daily_quota": 1000000,
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )
