"""Store a parcel under up to four quadrants: primary key becomes (parcel_id, quadkey).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("pk_parcel_quadkeys", "parcel_quadkeys", type_="primary")
    op.create_primary_key("pk_parcel_quadkeys", "parcel_quadkeys", ["parcel_id", "quadkey"])


def downgrade() -> None:
    op.execute("TRUNCATE parcel_quadkeys")  # several rows per parcel cannot fit the old key; rebuild the index after
    op.drop_constraint("pk_parcel_quadkeys", "parcel_quadkeys", type_="primary")
    op.create_primary_key("pk_parcel_quadkeys", "parcel_quadkeys", ["parcel_id"])
