"""User, role, and privilege management tools.

Recommended pattern: run the MCP server as a scoped, non-root user. Use these
tools (typically from an admin agent) to provision the agent's SQL user with
only the privileges it needs.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from src.common.config import get_flags
from src.common.connection import CockroachConnectionPool
from src.common.logging_config import get_logger
from src.common.server import mcp
from src.common.sql_safety import (
    UnsafeIdentifierError,
    quote_identifier,
    quote_qualified_identifier,
    validate_grant_target,
    validate_identifier,
    validate_privilege,
)
from src.common.tool_result import err, ok

log = get_logger("user_management")


def _require_writes_allowed() -> dict[str, Any] | None:
    if get_flags().read_only:
        return err("Server is in read-only mode; user management is disabled")
    return None


def _require_destructive_allowed(op: str) -> dict[str, Any] | None:
    flags = get_flags()
    if flags.read_only:
        return err(f"Server is in read-only mode; {op} is disabled")
    if not flags.allow_destructive:
        return err(f"{op} requires --allow-destructive at server startup")
    return None


@mcp.tool()
async def list_users(ctx: Context) -> dict[str, Any]:
    """List all users and roles defined in the cluster.

    Returns:
        Roster of users/roles with their attributes (login, admin, member-of).
    """
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT username, options, member_of
                FROM [SHOW USERS]
                ORDER BY username
                """
            )
        return ok(users=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("list_users failed")
        return err(exc)


@mcp.tool()
async def create_user(
    ctx: Context, username: str, password: str | None = None, with_login: bool = True
) -> dict[str, Any]:
    """Create a new SQL user.

    Args:
        username: Identifier-safe user name.
        password: Optional password. If omitted, the user is created without a
            password (still usable for certificate auth).
        with_login: Whether the user can log in interactively. Default True.
    """
    if block := _require_writes_allowed():
        return block
    try:
        ident = quote_identifier(username, kind="user")
    except UnsafeIdentifierError as exc:
        return err(exc)
    sql = f"CREATE USER IF NOT EXISTS {ident}"
    if not with_login:
        sql += " NOLOGIN"
    args: list[Any] = []
    if password is not None:
        sql += " WITH PASSWORD $1"
        args.append(password)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql, *args)
        return ok(message=f"User {username!r} created.")
    except Exception as exc:
        log.exception("create_user failed")
        return err(exc)


@mcp.tool()
async def drop_user(ctx: Context, username: str, confirm: bool = False) -> dict[str, Any]:
    """Drop a SQL user.

    Args:
        username: User name.
        confirm: Must be True. Refusal is the default.
    """
    if block := _require_destructive_allowed("drop_user"):
        return block
    if not confirm:
        return err(f"Refusing to drop user {username!r}: pass confirm=True to proceed")
    try:
        ident = quote_identifier(username, kind="user")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP USER IF EXISTS {ident}")
        return ok(message=f"User {username!r} dropped.")
    except Exception as exc:
        log.exception("drop_user failed")
        return err(exc)


@mcp.tool()
async def alter_user_password(ctx: Context, username: str, password: str) -> dict[str, Any]:
    """Set a user's password.

    Args:
        username: User name.
        password: New password.
    """
    if block := _require_writes_allowed():
        return block
    try:
        ident = quote_identifier(username, kind="user")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"ALTER USER {ident} WITH PASSWORD $1", password)
        return ok(message=f"Password updated for user {username!r}.")
    except Exception as exc:
        log.exception("alter_user_password failed")
        return err(exc)


@mcp.tool()
async def show_grants(ctx: Context, username: str | None = None) -> dict[str, Any]:
    """Show grants. If username given, filter to that user; otherwise show all.

    Args:
        username: Optional user to filter on.
    """
    if username is not None:
        try:
            validate_identifier(username, kind="user")
        except UnsafeIdentifierError as exc:
            return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        if username:
            sql = (
                "SELECT database_name, schema_name, object_name, object_type, "
                "grantee, privilege_type, is_grantable "
                f"FROM [SHOW GRANTS FOR {quote_identifier(username, kind='user')}]"
            )
            args: list[Any] = []
        else:
            sql = (
                "SELECT database_name, schema_name, object_name, object_type, "
                "grantee, privilege_type, is_grantable "
                "FROM [SHOW GRANTS]"
            )
            args = []
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return ok(grants=[dict(r) for r in rows], count=len(rows))
    except Exception as exc:
        log.exception("show_grants failed")
        return err(exc)


@mcp.tool()
async def grant_privileges(
    ctx: Context,
    privileges: list[str],
    target_type: str,
    target_name: str,
    grantee: str,
) -> dict[str, Any]:
    """Grant one or more privileges on an object to a user/role.

    Args:
        privileges: List of privilege names (e.g. ["SELECT", "INSERT"] or ["ALL"]).
        target_type: One of DATABASE, SCHEMA, TABLE, TYPE, SEQUENCE, FUNCTION.
        target_name: Object name. May be schema-qualified.
        grantee: User or role receiving the privilege.

    Example:
        grant_privileges(ctx, ["SELECT", "INSERT"], "TABLE", "public.users", "agent")
    """
    if block := _require_writes_allowed():
        return block
    try:
        if not privileges:
            return err("privileges list is empty")
        validated = [validate_privilege(p) for p in privileges]
        target_type_up = validate_grant_target(target_type)
        target_ident = quote_qualified_identifier(target_name, kind=target_type_up.lower())
        grantee_ident = quote_identifier(grantee, kind="grantee")
    except UnsafeIdentifierError as exc:
        return err(exc)
    privs_sql = ", ".join(validated)
    sql = f"GRANT {privs_sql} ON {target_type_up} {target_ident} TO {grantee_ident}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql)
        return ok(
            message=f"Granted {privs_sql} on {target_type_up} {target_name!r} to {grantee!r}."
        )
    except Exception as exc:
        log.exception("grant_privileges failed")
        return err(exc)


@mcp.tool()
async def revoke_privileges(
    ctx: Context,
    privileges: list[str],
    target_type: str,
    target_name: str,
    grantee: str,
    confirm: bool = False,
) -> dict[str, Any]:
    """Revoke one or more privileges from a user/role.

    Args:
        privileges: List of privilege names.
        target_type: One of DATABASE, SCHEMA, TABLE, TYPE, SEQUENCE, FUNCTION.
        target_name: Object name. May be schema-qualified.
        grantee: User or role losing the privilege.
        confirm: Must be True.
    """
    if block := _require_destructive_allowed("revoke_privileges"):
        return block
    if not confirm:
        return err("Refusing to revoke privileges: pass confirm=True to proceed")
    try:
        if not privileges:
            return err("privileges list is empty")
        validated = [validate_privilege(p) for p in privileges]
        target_type_up = validate_grant_target(target_type)
        target_ident = quote_qualified_identifier(target_name, kind=target_type_up.lower())
        grantee_ident = quote_identifier(grantee, kind="grantee")
    except UnsafeIdentifierError as exc:
        return err(exc)
    privs_sql = ", ".join(validated)
    sql = f"REVOKE {privs_sql} ON {target_type_up} {target_ident} FROM {grantee_ident}"
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(sql)
        return ok(message=f"Revoked {privs_sql} on {target_name!r} from {grantee!r}.")
    except Exception as exc:
        log.exception("revoke_privileges failed")
        return err(exc)


@mcp.tool()
async def create_role(ctx: Context, role_name: str) -> dict[str, Any]:
    """Create a new SQL role (a user that cannot log in by default).

    Args:
        role_name: Role name.
    """
    if block := _require_writes_allowed():
        return block
    try:
        ident = quote_identifier(role_name, kind="role")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE ROLE IF NOT EXISTS {ident}")
        return ok(message=f"Role {role_name!r} created.")
    except Exception as exc:
        log.exception("create_role failed")
        return err(exc)


@mcp.tool()
async def drop_role(ctx: Context, role_name: str, confirm: bool = False) -> dict[str, Any]:
    """Drop a SQL role.

    Args:
        role_name: Role name.
        confirm: Must be True.
    """
    if block := _require_destructive_allowed("drop_role"):
        return block
    if not confirm:
        return err(f"Refusing to drop role {role_name!r}: pass confirm=True to proceed")
    try:
        ident = quote_identifier(role_name, kind="role")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"DROP ROLE IF EXISTS {ident}")
        return ok(message=f"Role {role_name!r} dropped.")
    except Exception as exc:
        log.exception("drop_role failed")
        return err(exc)


@mcp.tool()
async def grant_role(ctx: Context, role_name: str, grantee: str) -> dict[str, Any]:
    """Grant a role to a user or another role.

    Args:
        role_name: Role being granted.
        grantee: User or role receiving the role.
    """
    if block := _require_writes_allowed():
        return block
    try:
        role_ident = quote_identifier(role_name, kind="role")
        grantee_ident = quote_identifier(grantee, kind="grantee")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"GRANT {role_ident} TO {grantee_ident}")
        return ok(message=f"Granted role {role_name!r} to {grantee!r}.")
    except Exception as exc:
        log.exception("grant_role failed")
        return err(exc)


@mcp.tool()
async def revoke_role(
    ctx: Context, role_name: str, grantee: str, confirm: bool = False
) -> dict[str, Any]:
    """Revoke a role from a user or another role.

    Args:
        role_name: Role being revoked.
        grantee: User or role losing the role.
        confirm: Must be True.
    """
    if block := _require_destructive_allowed("revoke_role"):
        return block
    if not confirm:
        return err("Refusing to revoke role: pass confirm=True to proceed")
    try:
        role_ident = quote_identifier(role_name, kind="role")
        grantee_ident = quote_identifier(grantee, kind="grantee")
    except UnsafeIdentifierError as exc:
        return err(exc)
    try:
        pool = await CockroachConnectionPool.get_connection_pool()
        async with pool.acquire() as conn:
            await conn.execute(f"REVOKE {role_ident} FROM {grantee_ident}")
        return ok(message=f"Revoked role {role_name!r} from {grantee!r}.")
    except Exception as exc:
        log.exception("revoke_role failed")
        return err(exc)
