"""SQL identifier validation and safe quoting helpers.

CockroachDB MCP tools receive identifier names (database, table, column, index,
view) and free-form filters from an LLM. Concatenating those into SQL is a
direct injection vector because LLM input can be steered by the end user
(prompt injection).

These helpers either validate that an identifier matches a strict regex and
double-quote it for safe inlining, or refuse the operation.

For VALUES (not identifiers), always use asyncpg parameterized queries with $1,
$2, etc. Never call any of these helpers on a value.
"""

from __future__ import annotations

import re

# A safe SQL identifier: starts with letter or underscore, then letters/digits/underscores.
# Length is capped at 63 (PostgreSQL/CockroachDB default).
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# A safe schema-qualified identifier: "schema.name" where both sides match _IDENT_RE.
_QUALIFIED_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}\.[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Allowed SSL modes for CockroachDB.
ALLOWED_SSL_MODES = frozenset({"disable", "allow", "prefer", "require", "verify-ca", "verify-full"})

# Allowed bulk-import URL schemes.
ALLOWED_IMPORT_SCHEMES = frozenset({"s3", "azure-blob", "azure", "gs", "http", "https"})

# Allowed output formats for execute_query.
ALLOWED_FORMATS = frozenset({"json", "csv", "table"})

# Vector similarity metric → CockroachDB operator.
VECTOR_METRIC_OPERATORS = {
    "cosine": "<=>",  # cosine distance
    "l2": "<->",  # Euclidean distance
    "ip": "<#>",  # negative inner product (rank-equivalent for unit vectors)
}
ALLOWED_VECTOR_METRICS = frozenset(VECTOR_METRIC_OPERATORS.keys()) | {"auto"}

# Vector index opclass per metric.
VECTOR_METRIC_OPCLASS = {
    "cosine": "vector_cosine_ops",
    "l2": "vector_l2_ops",
    "ip": "vector_ip_ops",
}

# Allowed SQL privileges that can be granted/revoked via tools.
ALLOWED_PRIVILEGES = frozenset(
    {
        "ALL",
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
        "USAGE",
        "CREATE",
        "CONNECT",
        "EXECUTE",
        "BACKUP",
        "RESTORE",
        "ZONECONFIG",
        "ADMIN",
        "MODIFYCLUSTERSETTING",
        "VIEWACTIVITY",
        "VIEWCLUSTERMETADATA",
        "VIEWCLUSTERSETTING",
        "CANCELQUERY",
        "NOSQLLOGIN",
    }
)

# Allowed target objects for GRANT/REVOKE.
ALLOWED_GRANT_TARGETS = frozenset({"DATABASE", "SCHEMA", "TABLE", "TYPE", "SEQUENCE", "FUNCTION"})

# Survival goals for multi-region databases.
ALLOWED_SURVIVAL_GOALS = frozenset({"ZONE", "REGION"})

# Table locality settings.
ALLOWED_LOCALITIES = frozenset({"REGIONAL", "REGIONAL_BY_ROW", "REGIONAL_BY_TABLE", "GLOBAL"})

# Sink schemes for CREATE CHANGEFEED.
ALLOWED_CHANGEFEED_SINKS = frozenset(
    {
        "kafka",
        "webhook-https",
        "webhook-http",
        "s3",
        "gs",
        "azure-blob",
        "azure",
        "experimental-sql",
        "external",
        "null",
    }
)

# Allowed BACKUP/RESTORE destination/source schemes.
ALLOWED_BACKUP_SCHEMES = frozenset(
    {"s3", "gs", "azure-blob", "azure", "nodelocal", "userfile", "external"}
)

# Allowed cluster setting types we expose for SET CLUSTER SETTING.
# We do NOT validate the name here (admins know what they're doing); we just
# refuse obvious shell-injection-shaped names downstream.
_CLUSTER_SETTING_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


def validate_cluster_setting_name(name: str) -> str:
    """Validate a cluster-setting name (e.g. kv.gc.ttl_seconds)."""
    if not isinstance(name, str) or not _CLUSTER_SETTING_NAME_RE.match(name):
        raise UnsafeIdentifierError(f"Invalid cluster setting name {name!r}")
    return name


def validate_vector_metric(metric: str | None) -> str:
    """Validate a vector similarity metric. Default 'cosine'."""
    if not metric:
        return "cosine"
    if metric not in ALLOWED_VECTOR_METRICS:
        raise UnsafeIdentifierError(
            f"Invalid metric {metric!r}; allowed: {sorted(ALLOWED_VECTOR_METRICS)}"
        )
    return metric


def validate_privilege(priv: str) -> str:
    """Validate a SQL privilege name (uppercase)."""
    if not isinstance(priv, str):
        raise UnsafeIdentifierError(f"Privilege must be a string, got {type(priv).__name__}")
    up = priv.upper()
    if up not in ALLOWED_PRIVILEGES:
        raise UnsafeIdentifierError(
            f"Invalid privilege {priv!r}; allowed: {sorted(ALLOWED_PRIVILEGES)}"
        )
    return up


def validate_grant_target(target: str) -> str:
    """Validate a GRANT target type (DATABASE/SCHEMA/TABLE/...)."""
    up = (target or "").upper()
    if up not in ALLOWED_GRANT_TARGETS:
        raise UnsafeIdentifierError(
            f"Invalid grant target {target!r}; allowed: {sorted(ALLOWED_GRANT_TARGETS)}"
        )
    return up


def validate_survival_goal(goal: str) -> str:
    """Validate a survival goal (ZONE/REGION)."""
    up = (goal or "").upper()
    if up not in ALLOWED_SURVIVAL_GOALS:
        raise UnsafeIdentifierError(
            f"Invalid survival goal {goal!r}; allowed: {sorted(ALLOWED_SURVIVAL_GOALS)}"
        )
    return up


def validate_locality(locality: str) -> str:
    """Validate a table locality setting."""
    up = (locality or "").upper().replace("-", "_")
    if up not in ALLOWED_LOCALITIES:
        raise UnsafeIdentifierError(
            f"Invalid locality {locality!r}; allowed: {sorted(ALLOWED_LOCALITIES)}"
        )
    return up


def validate_changefeed_sink(url: str) -> str:
    """Validate a CHANGEFEED sink URI by scheme."""
    import urllib.parse as _u

    parsed = _u.urlparse(url)
    if parsed.scheme not in ALLOWED_CHANGEFEED_SINKS:
        raise UnsafeIdentifierError(
            f"Unsupported changefeed sink scheme {parsed.scheme!r}; allowed: {sorted(ALLOWED_CHANGEFEED_SINKS)}"
        )
    return url


def validate_backup_uri(url: str) -> str:
    """Validate a BACKUP/RESTORE URI by scheme."""
    import urllib.parse as _u

    parsed = _u.urlparse(url)
    if parsed.scheme not in ALLOWED_BACKUP_SCHEMES:
        raise UnsafeIdentifierError(
            f"Unsupported backup URI scheme {parsed.scheme!r}; allowed: {sorted(ALLOWED_BACKUP_SCHEMES)}"
        )
    return url


def validate_node_id(node_id: int | str) -> int:
    """Validate a node ID (positive integer)."""
    try:
        n = int(node_id)
    except (TypeError, ValueError) as exc:
        raise UnsafeIdentifierError(f"Invalid node_id {node_id!r}") from exc
    if n < 1 or n > 100_000:
        raise UnsafeIdentifierError(f"node_id out of range: {n}")
    return n


def validate_job_id(job_id: int | str) -> int:
    """Validate a job ID (positive integer)."""
    try:
        n = int(job_id)
    except (TypeError, ValueError) as exc:
        raise UnsafeIdentifierError(f"Invalid job_id {job_id!r}") from exc
    if n < 1:
        raise UnsafeIdentifierError(f"job_id must be positive: {n}")
    return n


class UnsafeIdentifierError(ValueError):
    """Raised when an identifier fails validation."""


def validate_identifier(name: str, *, kind: str = "identifier") -> str:
    """Validate a SQL identifier and return it unchanged.

    Raises UnsafeIdentifierError if the name does not match _IDENT_RE.
    """
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise UnsafeIdentifierError(f"Invalid {kind} name {name!r}: must match {_IDENT_RE.pattern}")
    return name


def quote_identifier(name: str, *, kind: str = "identifier") -> str:
    """Validate then return a double-quoted identifier safe for SQL inlining.

    Use this only for identifiers (database, schema, table, column, index, view
    names). Never use this for values; use parameterized queries instead.
    """
    validate_identifier(name, kind=kind)
    return f'"{name}"'


def quote_qualified_identifier(name: str, *, kind: str = "identifier") -> str:
    """Validate then return a quoted schema.name identifier (or just name)."""
    if "." in name:
        if not _QUALIFIED_IDENT_RE.match(name):
            raise UnsafeIdentifierError(f"Invalid qualified {kind} name {name!r}")
        schema, ident = name.split(".", 1)
        return f'"{schema}"."{ident}"'
    return quote_identifier(name, kind=kind)


def validate_ssl_mode(mode: str | None) -> str:
    """Validate an SSL mode string. Returns 'disable' if mode is falsy."""
    if not mode:
        return "disable"
    if mode not in ALLOWED_SSL_MODES:
        raise UnsafeIdentifierError(
            f"Invalid SSL mode {mode!r}; allowed: {sorted(ALLOWED_SSL_MODES)}"
        )
    return mode


def validate_format(fmt: str | None) -> str:
    """Validate an output format. Returns 'json' if fmt is falsy."""
    if not fmt:
        return "json"
    if fmt not in ALLOWED_FORMATS:
        raise UnsafeIdentifierError(f"Invalid format {fmt!r}; allowed: {sorted(ALLOWED_FORMATS)}")
    return fmt


def validate_import_scheme(url_scheme: str) -> str:
    """Validate a bulk-import URL scheme."""
    if url_scheme not in ALLOWED_IMPORT_SCHEMES:
        raise UnsafeIdentifierError(
            f"Unsupported scheme: {url_scheme!r}; allowed: {sorted(ALLOWED_IMPORT_SCHEMES)}"
        )
    return url_scheme


# Interval format: minutes:seconds, where each side is digits up to 6 chars.
_INTERVAL_RE = re.compile(r"^\d{1,6}:\d{1,6}$")


def validate_interval(value: str, *, kind: str = "interval") -> str:
    """Validate a 'minutes:seconds' interval expression."""
    if not isinstance(value, str) or not _INTERVAL_RE.match(value):
        raise UnsafeIdentifierError(
            f"Invalid {kind} {value!r}: expected 'minutes:seconds' (e.g. '1:0')"
        )
    return value


def redact_dsn(dsn: str) -> str:
    """Return DSN with password component removed.

    Used in responses so the password is not echoed back to the agent or logs.
    """
    if not dsn:
        return dsn
    # asyncpg/PostgreSQL DSN form: scheme://user:password@host:port/db?params
    try:
        import urllib.parse as _u

        parsed = _u.urlparse(dsn)
        if parsed.password:
            netloc = parsed.hostname or ""
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            if parsed.username:
                netloc = f"{parsed.username}:***@{netloc}"
            redacted = parsed._replace(netloc=netloc)
            # Also strip password from query string if present
            if parsed.query:
                qs = _u.parse_qsl(parsed.query, keep_blank_values=True)
                qs = [(k, "***" if k.lower() == "password" else v) for k, v in qs]
                redacted = redacted._replace(query=_u.urlencode(qs))
            return _u.urlunparse(redacted)
        if parsed.query:
            qs = _u.parse_qsl(parsed.query, keep_blank_values=True)
            if any(k.lower() == "password" for k, _ in qs):
                qs = [(k, "***" if k.lower() == "password" else v) for k, v in qs]
                return _u.urlunparse(parsed._replace(query=_u.urlencode(qs)))
        return dsn
    except Exception:
        # If parsing fails, redact conservatively
        return "<dsn redacted>"
