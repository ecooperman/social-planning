"""users remember when they were last seen and on how many days (for the dashboard's stats)

Revision ID: g4c8d1e5a9b3
Revises: b3d5f7a9c1e2
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g4c8d1e5a9b3"
down_revision: Union[str, Sequence[str], None] = "b3d5f7a9c1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("active_days", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("active_days")
        batch_op.drop_column("last_seen_at")
