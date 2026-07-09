import pydantic


class QueueDepthResponse(pydantic.BaseModel):
    """
    Response from queue depth query.

    Provides information about the current ingestion queue status.
    """

    project_id: int = pydantic.Field(
        ...,
        description="Project ID",
    )

    queue_depth: int = pydantic.Field(
        ...,
        description="Number of logs currently waiting in the queue to be processed",
        ge=0,
    )

    model_config = pydantic.ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "project_id": 456,
                    "queue_depth": 1234,
                }
            ]
        }
    )
