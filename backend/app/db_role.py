"""Create or update the restricted role the app connects as, so row-level security applies to it.

Runs at startup as the database owner, after migrations (see the Dockerfile). Does nothing unless
APP_DB_PASSWORD is set. The role can read and write rows but owns nothing, so it can't change the schema
or the policies, and Postgres applies the policies to it.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.config import settings


def ensure_app_role(conn: Connection, user: str, password: str) -> None:
    exists = conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :u"), {"u": user})
    role = conn.dialect.identifier_preparer.quote(user)
    # Passwords can't be bound as parameters in DDL; quote it as a literal.
    literal = "'" + password.replace("'", "''") + "'"
    verb = "ALTER" if exists else "CREATE"
    conn.execute(text(f"{verb} ROLE {role} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS PASSWORD {literal}"))
    database = conn.dialect.identifier_preparer.quote(conn.scalar(text("SELECT current_database()")))
    conn.execute(text(f"GRANT CONNECT ON DATABASE {database} TO {role}"))
    conn.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
    conn.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"))
    conn.execute(text(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}"))
    if conn.scalar(text("SELECT to_regclass('public.alembic_version') IS NOT NULL")):
        conn.execute(text(f"REVOKE ALL ON alembic_version FROM {role}"))


def main() -> None:
    if not settings.app_db_password:
        return
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        ensure_app_role(conn, settings.app_db_user, settings.app_db_password)
    engine.dispose()


if __name__ == "__main__":
    main()
