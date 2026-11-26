"""supabase lockdown

Supabase exposes the public schema through its Data API (PostgREST). This app talks to
Postgres directly and never uses the Data API, so close it at the database level:
enable row level security on every table (deny by default, no policies) and revoke the
grants of the Supabase API roles. The app connects as the table owner, which bypasses RLS.

On plain Postgres (Neon, local) the API roles do not exist: only RLS is enabled.
SQLite is skipped.

Revision ID: c7d1e5a9f302
Revises: b2f0bc4315e9
Create Date: 2026-11-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d1e5a9f302'
down_revision = 'b2f0bc4315e9'
branch_labels = None
depends_on = None

_ROLES = ("anon", "authenticated")


def _tables(bind):
    quote = bind.dialect.identifier_preparer.quote
    return [quote(t) for t in sa.inspect(bind).get_table_names(schema="public")]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _tables(bind):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    for role in _ROLES:
        op.execute(f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};
                REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role};
              END IF;
            END $$;
        """)


def downgrade():
    # Grants are not restored on purpose: re-exposing the tables must be a deliberate act.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _tables(bind):
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
