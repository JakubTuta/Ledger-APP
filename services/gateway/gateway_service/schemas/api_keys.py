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
