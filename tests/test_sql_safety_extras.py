"""Tests for the new validators added for the expanded tool catalogue."""

from __future__ import annotations

import pytest

from src.common.sql_safety import (
    UnsafeIdentifierError,
    validate_backup_uri,
    validate_changefeed_sink,
    validate_cluster_setting_name,
    validate_grant_target,
    validate_job_id,
    validate_locality,
    validate_node_id,
    validate_privilege,
    validate_survival_goal,
    validate_vector_metric,
)


class TestValidateVectorMetric:
    @pytest.mark.parametrize("m", ["cosine", "l2", "ip", "auto"])
    def test_accepts(self, m: str) -> None:
        assert validate_vector_metric(m) == m

    def test_default(self) -> None:
        assert validate_vector_metric(None) == "cosine"
        assert validate_vector_metric("") == "cosine"

    def test_rejects_unknown(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_vector_metric("jaccard")

    def test_rejects_injection(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_vector_metric("cosine; DROP TABLE x")


class TestValidatePrivilege:
    @pytest.mark.parametrize("p", ["SELECT", "select", "INSERT", "ALL", "BACKUP"])
    def test_accepts_and_normalizes(self, p: str) -> None:
        assert validate_privilege(p) == p.upper()

    def test_rejects_unknown(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_privilege("DELETERIOUS")

    def test_rejects_non_string(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_privilege(123)  # type: ignore[arg-type]


class TestValidateGrantTarget:
    @pytest.mark.parametrize("t", ["DATABASE", "schema", "TABLE", "Type", "SEQUENCE", "FUNCTION"])
    def test_accepts(self, t: str) -> None:
        assert validate_grant_target(t) == t.upper()

    def test_rejects(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_grant_target("ROW")


class TestValidateSurvivalGoal:
    @pytest.mark.parametrize("g", ["ZONE", "REGION", "zone", "region"])
    def test_accepts(self, g: str) -> None:
        assert validate_survival_goal(g) == g.upper()

    def test_rejects(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_survival_goal("RACK")


class TestValidateLocality:
    @pytest.mark.parametrize(
        "loc",
        ["REGIONAL", "REGIONAL_BY_ROW", "REGIONAL_BY_TABLE", "GLOBAL", "regional"],
    )
    def test_accepts(self, loc: str) -> None:
        out = validate_locality(loc)
        assert out in {"REGIONAL", "REGIONAL_BY_ROW", "REGIONAL_BY_TABLE", "GLOBAL"}

    def test_rejects(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_locality("PER_NODE")


class TestValidateChangefeedSink:
    @pytest.mark.parametrize(
        "url",
        [
            "kafka://broker:9092/topic",
            "webhook-https://example.com/hook",
            "s3://bucket/path",
            "external://my-sink",
        ],
    )
    def test_accepts(self, url: str) -> None:
        assert validate_changefeed_sink(url) == url

    def test_rejects(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_changefeed_sink("ftp://server/path")


class TestValidateBackupUri:
    @pytest.mark.parametrize(
        "url",
        [
            "s3://bucket/path",
            "gs://bucket/p",
            "azure-blob://container/blob",
            "nodelocal://1/backup",
            "userfile:///backups/x",
        ],
    )
    def test_accepts(self, url: str) -> None:
        assert validate_backup_uri(url) == url

    def test_rejects(self) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_backup_uri("ftp://host/path")


class TestValidateClusterSettingName:
    @pytest.mark.parametrize(
        "n", ["kv.gc.ttl_seconds", "sql.defaults.serial_normalization", "_xyz"]
    )
    def test_accepts(self, n: str) -> None:
        assert validate_cluster_setting_name(n) == n

    @pytest.mark.parametrize("n", ["", "1abc", "kv;DROP", "name with space", "has-dash"])
    def test_rejects(self, n: str) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_cluster_setting_name(n)


class TestValidateNodeId:
    @pytest.mark.parametrize("v", [1, "5", 99999])
    def test_accepts(self, v) -> None:
        assert validate_node_id(v) >= 1

    @pytest.mark.parametrize("v", [0, -1, "abc", None, 100001])
    def test_rejects(self, v) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_node_id(v)


class TestValidateJobId:
    @pytest.mark.parametrize("v", [1, "999999999", 12345])
    def test_accepts(self, v) -> None:
        assert validate_job_id(v) >= 1

    @pytest.mark.parametrize("v", [0, -1, "abc", None])
    def test_rejects(self, v) -> None:
        with pytest.raises(UnsafeIdentifierError):
            validate_job_id(v)
