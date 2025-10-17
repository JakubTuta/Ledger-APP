import json

import ingestion_service.proto.ingestion_pb2 as ingestion_pb2


def create_proto_log(log_dict: dict) -> ingestion_pb2.LogEntry:
    """Convert a dictionary to a protobuf LogEntry message."""
    proto_log = ingestion_pb2.LogEntry(
        timestamp=log_dict.get("timestamp", ""),
        level=log_dict.get("level", "info"),
        log_type=log_dict.get("log_type", "logger"),
        importance=log_dict.get("importance", "standard"),
    )

    if "message" in log_dict and log_dict["message"] is not None:
        proto_log.message = log_dict["message"]
    if "error_type" in log_dict and log_dict["error_type"] is not None:
        proto_log.error_type = log_dict["error_type"]
    if "error_message" in log_dict and log_dict["error_message"] is not None:
        proto_log.error_message = log_dict["error_message"]
    if "stack_trace" in log_dict and log_dict["stack_trace"] is not None:
        proto_log.stack_trace = log_dict["stack_trace"]
    if "environment" in log_dict and log_dict["environment"] is not None:
        proto_log.environment = log_dict["environment"]
    if "release" in log_dict and log_dict["release"] is not None:
        proto_log.release = log_dict["release"]
    if "sdk_version" in log_dict and log_dict["sdk_version"] is not None:
        proto_log.sdk_version = log_dict["sdk_version"]
    if "platform" in log_dict and log_dict["platform"] is not None:
        proto_log.platform = log_dict["platform"]
    if "platform_version" in log_dict and log_dict["platform_version"] is not None:
        proto_log.platform_version = log_dict["platform_version"]
    if "attributes" in log_dict and log_dict["attributes"] is not None:
        proto_log.attributes = json.dumps(log_dict["attributes"])

    return proto_log
