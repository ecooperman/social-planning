"""add structured place fields to locations

Revision ID: c81f3a6d2e94
Revises: a3c9e1f4b2d7
Create Date: 2026-10-17 18:00:00.000000

Purely additive - every new column is nullable, so existing name-only
locations keep working and can be filled in later.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c81f3a6d2e94'
down_revision: Union[str, Sequence[str], None] = 'a3c9e1f4b2d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("region", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("country", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("latitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("longitude", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("place_id", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_locations_place_id", ["place_id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint("uq_locations_place_id", type_="unique")
        batch_op.drop_column("place_id")
        batch_op.drop_column("longitude")
        batch_op.drop_column("latitude")
        batch_op.drop_column("country")
        batch_op.drop_column("region")
        batch_op.drop_column("city")
