"""add plans.caption and parsed location fields

Revision ID: f2b8d6e4c1a9
Revises: e5a1c3f7b9d2
Create Date: 2026-10-18 12:00:00.000000

Purely additive - all nullable. Existing imported plans get these filled
in by re-running the extension's import with "Re-check posts already
imported" (see routers/instagram_import.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b8d6e4c1a9'
down_revision: Union[str, Sequence[str], None] = 'e5a1c3f7b9d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.add_column(sa.Column("caption", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("parsed_city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("parsed_region", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("parsed_country", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_column("parsed_country")
        batch_op.drop_column("parsed_region")
        batch_op.drop_column("parsed_city")
        batch_op.drop_column("caption")
