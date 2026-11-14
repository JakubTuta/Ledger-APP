import ledger_common.models.auth as auth_models
import ledger_common.models.logs as logs_models


def test_each_database_has_its_own_metadata():
    auth_tables = set(auth_models.Base.metadata.tables)
    logs_tables = set(logs_models.Base.metadata.tables)

    assert not auth_tables & logs_tables
    assert {"accounts", "projects", "api_keys", "alert_rules", "monitors"} <= auth_tables
    assert {
        "logs",
        "spans",
        "metric_points",
        "error_groups",
        "resources",
        "aggregated_metrics",
        "bottleneck_metrics",
        "log_facets_1h",
    } <= logs_tables


def test_hot_path_tables_are_range_partitioned():
    for name, column in (("logs", "timestamp"), ("spans", "start_time"), ("metric_points", "ts")):
        table = logs_models.Base.metadata.tables[name]
        assert table.dialect_options["postgresql"]["partition_by"] == f"RANGE ({column})"
