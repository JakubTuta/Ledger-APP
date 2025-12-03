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
    period: str | None = pydantic.Field(
        None,
        pattern=r"^(today|last7days|last30days|currentWeek|currentMonth|currentYear)$",
        description="Relative time period (mutually exclusive with periodFrom/periodTo)",
        examples=["today"],
    )
    periodFrom: str | None = pydantic.Field(
        None,
        description="Start of time range in ISO 8601 format (must be used with periodTo)",
        examples=["2024-01-15T00:00:00Z"],
    )
    periodTo: str | None = pydantic.Field(
        None,
        description="End of time range in ISO 8601 format (must be used with periodFrom)",
        examples=["2024-01-16T00:00:00Z"],
    )
    type: str = pydantic.Field(
        ...,
        pattern=r"^(logs|errors|metrics|error_list)$",
        description="Panel type: logs (log viewer), errors (error tracking aggregated), error_list (individual error entries), or metrics (charts/graphs)",
        examples=["errors"],
    )
    endpoint: str | None = pydantic.Field(
        None,
        description="Endpoint route (required for metrics type panels)",
        examples=["/api/v1/ingest/single"],
    )

    @pydantic.model_validator(mode="after")
    def validate_time_range(self):
        has_period = self.period is not None
        has_dates = self.periodFrom is not None and self.periodTo is not None

        if not has_period and not has_dates:
            raise ValueError(
                "Either 'period' or both 'periodFrom' and 'periodTo' must be provided"
            )

        if has_period and has_dates:
            raise ValueError(
                "Cannot use both 'period' and 'periodFrom'/'periodTo' parameters"
            )

        if (self.periodFrom is None) != (self.periodTo is None):
            raise ValueError(
                "Both 'periodFrom' and 'periodTo' must be provided together"
            )

        return self

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Error Rate - Today",
                    "index": 0,
                    "project_id": "456",
                    "period": "today",
                    "type": "errors",
                    "endpoint": None,
                },
                {
                    "name": "Endpoint Performance - Last 7 Days",
                    "index": 1,
                    "project_id": "456",
                    "period": "last7days",
                    "type": "metrics",
                    "endpoint": "/api/v1/ingest/single",
                },
                {
                    "name": "Custom Date Range Panel",
                    "index": 2,
                    "project_id": "456",
                    "periodFrom": "2024-01-15T00:00:00Z",
                    "periodTo": "2024-01-16T00:00:00Z",
                    "type": "logs",
                    "endpoint": None,
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
    period: str | None = pydantic.Field(None, description="Relative time period")
    periodFrom: str | None = pydantic.Field(None, description="Time range start (ISO 8601)")
    periodTo: str | None = pydantic.Field(None, description="Time range end (ISO 8601)")
    type: str = pydantic.Field(..., description="Panel type")
    endpoint: str | None = pydantic.Field(None, description="Endpoint route (for metrics panels)")

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": "panel_abc123",
                    "name": "Error Rate - Today",
                    "index": 0,
                    "project_id": "456",
                    "period": "today",
                    "periodFrom": None,
                    "periodTo": None,
                    "type": "errors",
                    "endpoint": None,
                },
                {
                    "id": "panel_def456",
                    "name": "Endpoint Performance - Last 7 Days",
                    "index": 1,
                    "project_id": "456",
                    "period": "last7days",
                    "periodFrom": None,
                    "periodTo": None,
                    "type": "metrics",
                    "endpoint": "/api/v1/ingest/single",
                },
                {
                    "id": "panel_ghi789",
                    "name": "Custom Date Range",
                    "index": 2,
                    "project_id": "456",
                    "period": None,
                    "periodFrom": "2024-01-15T00:00:00Z",
                    "periodTo": "2024-01-16T00:00:00Z",
                    "type": "logs",
                    "endpoint": None,
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
                            "endpoint": None,
                        },
                        {
                            "id": "panel_def456",
                            "name": "Endpoint Performance",
                            "index": 1,
                            "project_id": "456",
                            "time_range_from": "2024-01-15T00:00:00Z",
                            "time_range_to": "2024-01-16T00:00:00Z",
                            "type": "metrics",
                            "endpoint": "/api/v1/ingest/single",
                        }
                    ],
                    "total": 2,
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
    period: str | None = pydantic.Field(
        None,
        pattern=r"^(today|last7days|last30days|currentWeek|currentMonth|currentYear)$",
        description="Relative time period (mutually exclusive with periodFrom/periodTo)",
        examples=["today"],
    )
    periodFrom: str | None = pydantic.Field(
        None,
        description="Start of time range in ISO 8601 format (must be used with periodTo)",
        examples=["2024-01-15T00:00:00Z"],
    )
    periodTo: str | None = pydantic.Field(
        None,
        description="End of time range in ISO 8601 format (must be used with periodFrom)",
        examples=["2024-01-16T00:00:00Z"],
    )
    type: str = pydantic.Field(
        ...,
        pattern=r"^(logs|errors|metrics|error_list)$",
        description="Panel type (logs, errors, metrics, error_list)",
        examples=["errors"],
    )
    endpoint: str | None = pydantic.Field(
        None,
        description="Endpoint route (required for metrics type panels)",
        examples=["/api/v1/ingest/single"],
    )

    @pydantic.model_validator(mode="after")
    def validate_time_range(self):
        has_period = self.period is not None
        has_dates = self.periodFrom is not None and self.periodTo is not None

        if not has_period and not has_dates:
            raise ValueError(
                "Either 'period' or both 'periodFrom' and 'periodTo' must be provided"
            )

        if has_period and has_dates:
            raise ValueError(
                "Cannot use both 'period' and 'periodFrom'/'periodTo' parameters"
            )

        if (self.periodFrom is None) != (self.periodTo is None):
            raise ValueError(
                "Both 'periodFrom' and 'periodTo' must be provided together"
            )

        return self

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "Updated to Today",
                    "index": 0,
                    "project_id": "456",
                    "period": "today",
                    "type": "errors",
                    "endpoint": None,
                },
                {
                    "name": "Updated to Last 30 Days",
                    "index": 1,
                    "project_id": "456",
                    "period": "last30days",
                    "type": "metrics",
                    "endpoint": "/api/v1/ingest/batch",
                },
                {
                    "name": "Updated to Custom Dates",
                    "index": 2,
                    "project_id": "456",
                    "time_range_from": "2024-01-08T00:00:00Z",
                    "time_range_to": "2024-01-15T00:00:00Z",
                    "type": "logs",
                    "endpoint": None,
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
