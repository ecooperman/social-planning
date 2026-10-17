"""rename ideas to plans, add locations

Revision ID: a3c9e1f4b2d7
Revises: 151b192521e2
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9e1f4b2d7'
down_revision: Union[str, Sequence[str], None] = '151b192521e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("ideas", "plans")

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_locations_name"),
    )

    with op.batch_alter_table("plans") as batch_op:
        batch_op.add_column(sa.Column("location_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_plans_location_id_locations", "locations", ["location_id"], ["id"]
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("plans") as batch_op:
        batch_op.drop_constraint("fk_plans_location_id_locations", type_="foreignkey")
        batch_op.drop_column("location_id")

    op.drop_table("locations")
    op.rename_table("plans", "ideas")
