"""users, and every person's data belongs to one of them

Until now the app was private to its one administrator and nothing in it had an owner. Now several people can have
accounts, each with their own completely private data: users, and an owner on countries, regions, cities, locations
and plans.

Everything that exists now is parked on a placeholder user (legacy-owner@plans.invalid); the first administrator to
sign in takes the placeholder over by giving it their email (app/crud.py adopt_or_create_admin), so it all becomes
theirs without moving a row.

Country and location names (and a location's Google place id) go from unique across the whole table to unique per
owner, since two people may each have a "Canada" or a "Salem, MA".

Revision ID: b3d5f7a9c1e2
Revises: f2b8d6e4c1a9
Create Date: 2026-11-17 09:00:00.000000

"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3d5f7a9c1e2"
down_revision: Union[str, Sequence[str], None] = "f2b8d6e4c1a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_OWNER_EMAIL = "legacy-owner@plans.invalid"
OWNED = ("countries", "regions", "cities", "locations", "plans")

# SQLite reports the old unnamed UNIQUE constraints only if told how they would have been named, which lets batch mode drop them.
NAMING = {"uq": "uq_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    conn = op.get_bind()
    conn.execute(
        sa.text("INSERT INTO users (email, status, created_at) VALUES (:email, 'active', :now)"),
        {"email": LEGACY_OWNER_EMAIL, "now": datetime.utcnow()},
    )
    legacy_id = conn.execute(sa.text("SELECT id FROM users WHERE email = :e"), {"e": LEGACY_OWNER_EMAIL}).scalar()

    # owner_id starts nullable so the existing rows can be filled in.
    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(f"fk_{table}_owner_id_users", "users", ["owner_id"], ["id"])
        conn.execute(sa.text(f"UPDATE {table} SET owner_id = :owner"), {"owner": legacy_id})

    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.alter_column("owner_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_index(f"ix_{table}_owner_id", ["owner_id"])

    with op.batch_alter_table("countries", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("uq_countries_name", type_="unique")
        batch_op.create_unique_constraint("uq_countries_owner_id_name", ["owner_id", "name"])
    with op.batch_alter_table("locations", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("uq_locations_name", type_="unique")
        batch_op.drop_constraint("uq_locations_place_id", type_="unique")
        batch_op.create_unique_constraint("uq_locations_owner_id_name", ["owner_id", "name"])
        batch_op.create_unique_constraint("uq_locations_owner_id_place_id", ["owner_id", "place_id"])


def downgrade() -> None:
    """Downgrade schema. Fails if two people have a country, location or place id in common (the old schema had one
    table-wide namespace), and everyone's data ends up in one place."""
    with op.batch_alter_table("locations", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("uq_locations_owner_id_place_id", type_="unique")
        batch_op.drop_constraint("uq_locations_owner_id_name", type_="unique")
        batch_op.create_unique_constraint("uq_locations_name", ["name"])
        batch_op.create_unique_constraint("uq_locations_place_id", ["place_id"])
    with op.batch_alter_table("countries", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("uq_countries_owner_id_name", type_="unique")
        batch_op.create_unique_constraint("uq_countries_name", ["name"])
    for table in OWNED:
        with op.batch_alter_table(table, naming_convention=NAMING) as batch_op:
            batch_op.drop_index(f"ix_{table}_owner_id")
            batch_op.drop_constraint(f"fk_{table}_owner_id_users", type_="foreignkey")
            batch_op.drop_column("owner_id")
    op.drop_table("users")
