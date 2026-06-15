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
