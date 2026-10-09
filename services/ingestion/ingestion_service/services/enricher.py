import datetime
import hashlib
import re

import ingestion_service.schemas as schemas


def generate_error_fingerprint(log_entry: schemas.LogEntry) -> str | None:
    if log_entry.log_type != "exception" or not log_entry.stack_trace:
        return None

    stack_frames = parse_stack_trace(log_entry.stack_trace)

    innermost_frames = stack_frames[:3]
    frame_signature = "|".join([f"{frame['file']}:{frame['line']}" for frame in innermost_frames])

    platform = log_entry.platform or "unknown"
    error_type = log_entry.error_type or "UnknownError"

    signature = f"{error_type}:{frame_signature}:{platform}"

    return hashlib.sha256(signature.encode()).hexdigest()


def parse_stack_trace(stack_trace: str) -> list[dict[str, str]]:
    """Frames ordered innermost (where the error was raised) first."""
    frames = []

    # Python prints the outermost frame first ("most recent call last"), the
    # opposite of Node and Java. Taken as-is, the leading frames of every web
    # request's traceback are the same framework entry points, which merged
    # unrelated errors of one exception type into a single group.
    python_pattern = r'File "([^"]+)", line (\d+)'
    matches = re.findall(python_pattern, stack_trace)
    for file_path, line_number in reversed(matches):
        frames.append({"file": file_path, "line": line_number})

    if not frames:
        node_pattern = r"at .+ \(([^:]+):(\d+):\d+\)"
        matches = re.findall(node_pattern, stack_trace)
        for file_path, line_number in matches:
            frames.append({"file": file_path, "line": line_number})

    if not frames:
        java_pattern = r"at .+\(([^:]+):(\d+)\)"
        matches = re.findall(java_pattern, stack_trace)
        for file_path, line_number in matches:
            frames.append({"file": file_path, "line": line_number})

    return frames


def enrich_log_entry(log_entry: schemas.LogEntry, project_id: int) -> schemas.EnrichedLogEntry:
    error_fingerprint = generate_error_fingerprint(log_entry)

    return schemas.EnrichedLogEntry(
        project_id=project_id,
        log_entry=log_entry,
        ingested_at=datetime.datetime.now(datetime.timezone.utc),
        error_fingerprint=error_fingerprint,
    )
