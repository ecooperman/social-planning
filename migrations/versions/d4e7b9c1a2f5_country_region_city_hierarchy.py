"""country -> region -> city hierarchy for locations

Revision ID: d4e7b9c1a2f5
Revises: c81f3a6d2e94
Create Date: 2026-10-17 20:00:00.000000

Replaces the free-text city/region/country columns c81f3a6d2e94 added to
locations with links into three new managed lists. Existing text values are
carried over (matched ignoring case, so "united states" and "United States"
become one country) before the text columns are dropped. A region or city
with no country to hang under can't be represented in the hierarchy and is
dropped - on the way down, the text columns are rebuilt from the links.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e7b9c1a2f5'
down_revision: Union[str, Sequence[str], None] = 'c81f3a6d2e94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _clean(value):
    value = (value or "").strip()
    return value or None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "countries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_countries_name"),
    )
    op.create_table(
        "regions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], name="fk_regions_country_id_countries"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id", "name", name="uq_regions_country_name"),
    )
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], name="fk_cities_country_id_countries"),
        sa.ForeignKeyConstraint(["region_id"], ["regions.id"], name="fk_cities_region_id_regions"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id", "region_id", "name", name="uq_cities_parent_name"),
    )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(sa.Column("country_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("region_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("city_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_locations_country_id_countries", "countries", ["country_id"], ["id"])
        batch_op.create_foreign_key("fk_locations_region_id_regions", "regions", ["region_id"], ["id"])
        batch_op.create_foreign_key("fk_locations_city_id_cities", "cities", ["city_id"], ["id"])

    # Carry the free-text values over into the hierarchy.
    conn = op.get_bind()
    countries, regions, cities = {}, {}, {}

    def find_or_create(cache, key, table, values):
        if key not in cache:
            result = conn.execute(sa.text(f"INSERT INTO {table} ({', '.join(values)}) VALUES ({', '.join(':' + k for k in values)})"), values)
            cache[key] = result.lastrowid
        return cache[key]

    rows = conn.execute(sa.text("SELECT id, city, region, country FROM locations")).fetchall()
    for loc_id, city, region, country in rows:
        city, region, country = _clean(city), _clean(region), _clean(country)
        if not country:
            continue
        country_id = find_or_create(countries, country.lower(), "countries", {"name": country})
        region_id = None
        if region:
            region_id = find_or_create(regions, (country_id, region.lower()), "regions", {"name": region, "country_id": country_id})
        city_id = None
        if city:
            city_id = find_or_create(
                cities, (country_id, region_id, city.lower()), "cities",
                {"name": city, "country_id": country_id, "region_id": region_id},
            )
        conn.execute(
            sa.text("UPDATE locations SET country_id = :c, region_id = :r, city_id = :ci WHERE id = :id"),
            {"c": country_id, "r": region_id, "ci": city_id, "id": loc_id},
        )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_column("city")
        batch_op.drop_column("region")
        batch_op.drop_column("country")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("locations") as batch_op:
        batch_op.add_column(sa.Column("city", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("region", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("country", sa.String(), nullable=True))

    op.execute(
        "UPDATE locations SET "
        "country = (SELECT name FROM countries WHERE countries.id = locations.country_id), "
        "region = (SELECT name FROM regions WHERE regions.id = locations.region_id), "
        "city = (SELECT name FROM cities WHERE cities.id = locations.city_id)"
    )

    with op.batch_alter_table("locations") as batch_op:
        batch_op.drop_constraint("fk_locations_city_id_cities", type_="foreignkey")
        batch_op.drop_constraint("fk_locations_region_id_regions", type_="foreignkey")
        batch_op.drop_constraint("fk_locations_country_id_countries", type_="foreignkey")
        batch_op.drop_column("city_id")
        batch_op.drop_column("region_id")
        batch_op.drop_column("country_id")

    op.drop_table("cities")
    op.drop_table("regions")
    op.drop_table("countries")
