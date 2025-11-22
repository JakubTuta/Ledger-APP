import pydantic


class PanelRequest(pydantic.BaseModel):
    """Request body for creating a dashboard panel."""

    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Panel display name",
        examples=["Error Rate - Last 24h"],
    )
    index: int = pydantic.Field(
        ..., ge=0, description="Panel position index (0-based)", examples=[0]
    )
    project_id: str = pydantic.Field(
        ..., min_length=1, description="Project ID to display data from", examples=["456"]
    )
    time_range_from: str = pydantic.Field(
        ...,
        description="Start of time range (ISO 8601 format)",
        examples=["2024-01-15T00:00:00Z"],
    )
    time_range_to: str = pydantic.Field(
        ...,
        description="End of time range (ISO 8601 format)",
        examples=["2024-01-16T00:00:00Z"],
    )
    type: str = pydantic.Field(
        ...,
        pattern=r"^(logs|errors|metrics)$",
        description="Panel type: logs (log viewer), errors (error tracking), or metrics (charts/graphs)",
        examples=["errors"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Error Rate - Last 24h",
                    "index": 0,
                    "project_id": "456",
                    "time_range_from": "2024-01-15T00:00:00Z",
                    "time_range_to": "2024-01-16T00:00:00Z",
                    "type": "errors",
                }
            ]
        }
    )


class PanelResponse(pydantic.BaseModel):
    """Dashboard panel details."""

    id: str = pydantic.Field(..., description="Unique panel identifier")
    name: str = pydantic.Field(..., description="Panel display name")
    index: int = pydantic.Field(..., description="Panel position index")
    project_id: str = pydantic.Field(..., description="Associated project ID")
    time_range_from: str = pydantic.Field(..., description="Time range start")
    time_range_to: str = pydantic.Field(..., description="Time range end")
    type: str = pydantic.Field(..., description="Panel type")
    available_routes: list[str] = pydantic.Field(
        default_factory=list,
        description="List of unique API endpoint routes (e.g., 'GET /api/v1/users') available for this panel's project. Populated by analytics workers from endpoint logs.",
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "panel_abc123",
                    "name": "Error Rate - Last 24h",
                    "index": 0,
                    "project_id": "456",
                    "time_range_from": "2024-01-15T00:00:00Z",
                    "time_range_to": "2024-01-16T00:00:00Z",
                    "type": "errors",
                    "available_routes": [
                        "GET /api/v1/users",
                        "POST /api/v1/orders",
                        "GET /api/v1/products/:id",
                    ],
                }
            ]
        }
    )


class PanelListResponse(pydantic.BaseModel):
    """Response containing list of dashboard panels."""

    panels: list[PanelResponse] = pydantic.Field(..., description="List of panels")
    total: int = pydantic.Field(..., description="Total number of panels")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "panels": [
                        {
                            "id": "panel_abc123",
                            "name": "Error Rate - Last 24h",
                            "index": 0,
                            "project_id": "456",
                            "time_range_from": "2024-01-15T00:00:00Z",
                            "time_range_to": "2024-01-16T00:00:00Z",
                            "type": "errors",
                            "available_routes": [
                                "GET /api/v1/users",
                                "POST /api/v1/orders",
                            ],
                        }
                    ],
                    "total": 1,
                }
            ]
        }
    )


class UpdatePanelRequest(pydantic.BaseModel):
    """Request body for updating a dashboard panel."""

    name: str = pydantic.Field(
        ...,
        min_length=1,
        max_length=255,
        description="Panel display name",
        examples=["Error Rate - Last 24h"],
    )
    index: int = pydantic.Field(
        ..., ge=0, description="Panel position index", examples=[0]
    )
    project_id: str = pydantic.Field(
        ..., min_length=1, description="Project ID", examples=["456"]
    )
    time_range_from: str = pydantic.Field(
        ...,
        description="Start of time range (ISO 8601)",
        examples=["2024-01-15T00:00:00Z"],
    )
    time_range_to: str = pydantic.Field(
        ...,
        description="End of time range (ISO 8601)",
        examples=["2024-01-16T00:00:00Z"],
    )
    type: str = pydantic.Field(
        ...,
        pattern=r"^(logs|errors|metrics)$",
        description="Panel type (logs, errors, metrics)",
        examples=["errors"],
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Updated Error Rate - Last 48h",
                    "index": 0,
                    "project_id": "456",
                    "time_range_from": "2024-01-13T00:00:00Z",
                    "time_range_to": "2024-01-15T00:00:00Z",
                    "type": "errors",
                }
            ]
        }
    )


class DeletePanelResponse(pydantic.BaseModel):
    """Response confirming panel deletion."""

    success: bool = pydantic.Field(..., description="Whether deletion succeeded")
    message: str = pydantic.Field(..., description="Status message")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "success": True,
                    "message": "Panel panel_abc123 deleted successfully",
                }
            ]
        }
    )
