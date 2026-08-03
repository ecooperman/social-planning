"""baseline schema

Revision ID: 151b192521e2
Revises:
Create Date: 2026-07-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '151b192521e2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ideas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("event_date", sa.DateTime(), nullable=True),
        sa.Column(
            "scrape_status",
            sa.Enum("not_started", "success", "failed", "unsupported", name="scrapestatus"),
            nullable=False,
        ),
        sa.Column("scraped_title", sa.String(), nullable=True),
        sa.Column("scraped_description", sa.String(), nullable=True),
        sa.Column("scraped_image_url", sa.String(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(), nullable=True),
        sa.Column("scrape_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ideas")
