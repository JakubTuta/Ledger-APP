import pydantic


class CreateApiKeyRequest(pydantic.BaseModel):
    """Request body for creating a new API key."""

    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Descriptive name for the API key",
        examples=["Production API Key"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={"examples": [{"name": "Production API Key"}]}
    )


class CreateApiKeyResponse(pydantic.BaseModel):
    """Response containing newly created API key."""

    key_id: int = pydantic.Field(..., description="Unique API key identifier")
    full_key: str = pydantic.Field(
        ...,
        description="Complete API key - ONLY shown once! Save it immediately.",
    )
    key_prefix: str = pydantic.Field(..., description="Key prefix for identification")
    warning: str = pydantic.Field(
        default="Save this key now! It will not be shown again.",
        description="Security warning about key visibility",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key_id": 789,
                    "full_key": "ledger_prod_1a2b3c4d5e6f7g8h9i0j",
                    "key_prefix": "ledger_prod_1a2b",
                    "warning": "Save this key now! It will not be shown again.",
                }
            ]
        }
    )


class RevokeApiKeyResponse(pydantic.BaseModel):
    """Response confirming API key revocation."""

    success: bool = pydantic.Field(..., description="Whether revocation succeeded")
    message: str = pydantic.Field(..., description="Status message")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": True,
                    "message": "API key 789 has been revoked",
                }
            ]
        }
    )


class ApiKeyInfo(pydantic.BaseModel):
    """Information about a single API key."""

    key_id: int = pydantic.Field(..., description="Unique API key identifier")
    project_id: int = pydantic.Field(..., description="Project ID this key belongs to")
    name: str = pydantic.Field(..., description="Descriptive name for the API key")
    key_prefix: str = pydantic.Field(..., description="Key prefix for identification")
    status: str = pydantic.Field(..., description="API key status (active, revoked)")
    created_at: str = pydantic.Field(..., description="When the key was created")
    last_used_at: str | None = pydantic.Field(
        None, description="When the key was last used (if ever)"
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "key_id": 789,
                    "project_id": 456,
                    "name": "Production API Key",
                    "key_prefix": "ledger_prod_1a2b",
                    "status": "active",
                    "created_at": "2024-01-15T10:30:00Z",
                    "last_used_at": "2024-01-20T15:45:00Z",
                }
            ]
        }
    )


class ListApiKeysResponse(pydantic.BaseModel):
    """Response containing list of API keys."""

    api_keys: list[ApiKeyInfo] = pydantic.Field(
        ..., description="List of API keys for the project"
    )
    total: int = pydantic.Field(..., description="Total number of API keys")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "api_keys": [
                        {
                            "key_id": 789,
                            "project_id": 456,
                            "name": "Production API Key",
                            "key_prefix": "ledger_prod_1a2b",
                            "status": "active",
                            "created_at": "2024-01-15T10:30:00Z",
                            "last_used_at": "2024-01-20T15:45:00Z",
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )
