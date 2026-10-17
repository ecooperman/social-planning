"""add plans.imported flag

Revision ID: e5a1c3f7b9d2
Revises: d4e7b9c1a2f5
Create Date: 2026-10-18 10:00:00.000000

Backfills the flag for plans the Instagram import already created, which
predate it. Those are recognizable by the exact URL shape the importer
writes - its canonical https://www.instagram.com/p/<code>/ (or /reel/)
with nothing after the trailing slash - plus a location, which the import
sets for the whole batch. Hand-added plans pasted from the Instagram app
carry the username path or a ?igsh= tracking suffix instead, and none of
them had a location before the import existed.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a1c3f7b9d2'
down_revision: Union[str, Sequence[str], None] = 'd4e7b9c1a2f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.add_column(sa.Column("imported", sa.Boolean(), nullable=False, server_default="0"))

    op.execute(
        "UPDATE plans SET imported = 1 "
        "WHERE location_id IS NOT NULL "
        "AND (url GLOB 'https://www.instagram.com/p/*/' OR url GLOB 'https://www.instagram.com/reel/*/') "
        "AND url NOT GLOB '*[?#]*' "
        "AND url NOT GLOB 'https://www.instagram.com/p/*/*/' "
        "AND url NOT GLOB 'https://www.instagram.com/reel/*/*/'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_column("imported")
