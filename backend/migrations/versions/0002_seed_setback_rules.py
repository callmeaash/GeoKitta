"""Seed setback rules (FIG 2017 Banepa case study).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

setback_rules = sa.table(
    "setback_rules",
    sa.column("feature_type", sa.String),
    sa.column("distance_m", sa.Numeric),
    sa.column("measured_from", sa.String),
    sa.column("source", sa.String),
    sa.column("note", sa.Text),
)

RULES = [
    {"feature_type": "highway", "distance_m": 25.00, "measured_from": "centre_line", "source": "national",
     "note": "82 ft from the centre line (national highway standard)"},
    {"feature_type": "highway", "distance_m": 22.86, "measured_from": "centre_line", "source": "municipal",
     "note": "75 ft from the centre line (municipal rule)"},
    {"feature_type": "river", "distance_m": 15.00, "measured_from": "bank", "source": "municipal",
     "note": "15 m from each bank"},
    {"feature_type": "stream", "distance_m": 7.00, "measured_from": "bank", "source": "municipal",
     "note": "7 m from each bank"},
    {"feature_type": "power_line", "distance_m": 9.00, "measured_from": "line", "source": "national",
     "note": "132 kV line corridor, 30 ft"},
]


def upgrade() -> None:
    op.bulk_insert(setback_rules, RULES)


def downgrade() -> None:
    op.execute(
        "DELETE FROM setback_rules WHERE (feature_type, source) IN ("
        "('highway', 'national'), ('highway', 'municipal'), ('river', 'municipal'), "
        "('stream', 'municipal'), ('power_line', 'national'))"
    )
