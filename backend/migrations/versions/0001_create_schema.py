"""Create schema (14 tables).

Revision ID: 0001
Revises:
Create Date: 2026-11-12
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table('features',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=True),
    sa.Column('feature_type', sa.String(length=20), nullable=False),
    sa.Column('width_m', sa.Numeric(precision=6, scale=2), nullable=True, comment='needed for setbacks measured from the bank'),
    sa.Column('geom', Geometry(geometry_type='LINESTRING', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('osm_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("feature_type IN ('highway', 'road', 'river', 'stream', 'power_line')", name=op.f('ck_features_feature_type')),
    sa.CheckConstraint('width_m IS NULL OR width_m > 0', name=op.f('ck_features_width_m')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_features'))
    )
    op.create_table('officers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False, comment='argon2 hash; never the password itself'),
    sa.Column('full_name', sa.String(length=100), nullable=False),
    sa.Column('office', sa.String(length=100), nullable=True),
    sa.Column('is_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("username ~ '^[a-z][a-z0-9_.]{2,49}$'", name=op.f('ck_officers_username_format')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_officers')),
    sa.UniqueConstraint('username', name=op.f('uq_officers_username'))
    )
    op.create_table('owners',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lin', sa.String(length=20), nullable=False, comment='Landowner Identification Number'),
    sa.Column('owner_type', sa.String(length=20), nullable=False),
    sa.Column('full_name', sa.String(length=150), nullable=False),
    sa.Column('full_name_ne', sa.String(length=150), nullable=True, comment='name in Devanagari'),
    sa.Column('gender', sa.String(length=10), nullable=True),
    sa.Column('date_of_birth', sa.Date(), nullable=True),
    sa.Column('citizenship_no', sa.String(length=30), nullable=True),
    sa.Column('district_code', sa.SmallInteger(), nullable=True),
    sa.Column('address', sa.Text(), nullable=True),
    sa.Column('phone', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("gender IN ('male', 'female', 'other')", name=op.f('ck_owners_gender')),
    sa.CheckConstraint("owner_type <> 'individual' OR date_of_birth IS NOT NULL", name=op.f('ck_owners_individual_dob')),
    sa.CheckConstraint("owner_type IN ('individual', 'organisation', 'government', 'communal')", name=op.f('ck_owners_owner_type')),
    sa.CheckConstraint('district_code BETWEEN 1 AND 77', name=op.f('ck_owners_district_code')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_owners')),
    sa.UniqueConstraint('lin', name=op.f('uq_owners_lin'))
    )
    op.create_table('parcels',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('pin', sa.String(length=30), nullable=False, comment='Parcel Identification Number'),
    sa.Column('district_code', sa.SmallInteger(), nullable=False),
    sa.Column('municipality_code', sa.Integer(), nullable=False),
    sa.Column('ward_no', sa.SmallInteger(), nullable=False),
    sa.Column('map_sheet_code', sa.String(length=9), nullable=False, comment='9-digit map sheet geocode (GRIDS1-style)'),
    sa.Column('parcel_no', sa.Integer(), nullable=False, comment='kitta number'),
    sa.Column('parcel_type', sa.String(length=20), nullable=False),
    sa.Column('land_use', sa.String(length=20), nullable=False),
    sa.Column('registered_area', sa.Numeric(precision=12, scale=2), nullable=False, comment='m², as recorded'),
    sa.Column('status', sa.String(length=10), server_default=sa.text("'active'"), nullable=False),
    sa.Column('boundary', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False, comment='single polygon, EPSG:4326; must be valid'),
    sa.Column('geometry_source', sa.String(length=20), server_default=sa.text("'field_survey'"), nullable=False),
    sa.Column('accuracy_m', sa.Numeric(precision=6, scale=3), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("geometry_source IN ('field_survey', 'digitized', 'synthetic')", name=op.f('ck_parcels_geometry_source')),
    sa.CheckConstraint("land_use IN ('residential', 'commercial', 'agricultural', 'institutional', 'other')", name=op.f('ck_parcels_land_use')),
    sa.CheckConstraint("map_sheet_code ~ '^[0-9]{9}$'", name=op.f('ck_parcels_map_sheet_code')),
    sa.CheckConstraint("parcel_type IN ('private', 'public', 'government', 'guthi')", name=op.f('ck_parcels_parcel_type')),
    sa.CheckConstraint("status IN ('active', 'retired')", name=op.f('ck_parcels_status')),
    sa.CheckConstraint('ST_IsValid(boundary)', name=op.f('ck_parcels_boundary_valid')),
    sa.CheckConstraint('accuracy_m IS NULL OR accuracy_m > 0', name=op.f('ck_parcels_accuracy_m')),
    sa.CheckConstraint('district_code BETWEEN 1 AND 77', name=op.f('ck_parcels_district_code')),
    sa.CheckConstraint('parcel_no > 0', name=op.f('ck_parcels_parcel_no')),
    sa.CheckConstraint('registered_area > 0', name=op.f('ck_parcels_registered_area')),
    sa.CheckConstraint('ward_no BETWEEN 1 AND 40', name=op.f('ck_parcels_ward_no')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parcels')),
    sa.UniqueConstraint('municipality_code', 'ward_no', 'map_sheet_code', 'parcel_no', name='uq_parcels_kitta'),
    sa.UniqueConstraint('pin', name=op.f('uq_parcels_pin'))
    )
    op.create_table('places',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=150), nullable=False),
    sa.Column('name_ne', sa.String(length=150), nullable=True, comment='name in Devanagari'),
    sa.Column('place_type', sa.String(length=20), nullable=False),
    sa.Column('ward_no', sa.SmallInteger(), nullable=True),
    sa.Column('location', Geometry(geometry_type='POINT', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('osm_id', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("place_type IN ('tole', 'landmark', 'park', 'river', 'road', 'ward')", name=op.f('ck_places_place_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_places'))
    )
    op.create_table('setback_rules',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('feature_type', sa.String(length=20), nullable=False),
    sa.Column('distance_m', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('measured_from', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.CheckConstraint("feature_type IN ('highway', 'road', 'river', 'stream', 'power_line')", name=op.f('ck_setback_rules_feature_type')),
    sa.CheckConstraint("measured_from IN ('centre_line', 'bank', 'line')", name=op.f('ck_setback_rules_measured_from')),
    sa.CheckConstraint("source IN ('municipal', 'national')", name=op.f('ck_setback_rules_source')),
    sa.CheckConstraint('distance_m > 0', name=op.f('ck_setback_rules_distance_m')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_setback_rules')),
    sa.UniqueConstraint('feature_type', 'source', name='uq_setback_rules_feature_source')
    )
    op.create_table('parcel_issues',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parcel_id', sa.Integer(), nullable=False),
    sa.Column('other_parcel_id', sa.Integer(), nullable=True, comment='the other parcel, for overlaps'),
    sa.Column('issue_type', sa.String(length=20), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('review_status', sa.String(length=10), server_default=sa.text("'open'"), nullable=False),
    sa.Column('review_note', sa.Text(), nullable=True),
    sa.Column('found_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reviewed_by', sa.Integer(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("issue_type IN ('overlap', 'gap', 'sliver', 'invalid', 'area_mismatch')", name=op.f('ck_parcel_issues_issue_type')),
    sa.CheckConstraint("review_status IN ('open', 'resolved', 'dispute')", name=op.f('ck_parcel_issues_review_status')),
    sa.CheckConstraint("severity IN ('error', 'warning')", name=op.f('ck_parcel_issues_severity')),
    sa.CheckConstraint('other_parcel_id IS NULL OR other_parcel_id <> parcel_id', name=op.f('ck_parcel_issues_other_parcel')),
    sa.ForeignKeyConstraint(['other_parcel_id'], ['parcels.id'], name=op.f('fk_parcel_issues_other_parcel_id_parcels')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_parcel_issues_parcel_id_parcels')),
    sa.ForeignKeyConstraint(['reviewed_by'], ['officers.id'], name=op.f('fk_parcel_issues_reviewed_by_officers')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parcel_issues'))
    )
    op.create_index(op.f('ix_parcel_issues_parcel_id'), 'parcel_issues', ['parcel_id'], unique=False)
    op.create_table('parcel_quadkeys',
    sa.Column('parcel_id', sa.Integer(), nullable=False),
    sa.Column('quadkey', sa.String(length=24, collation='C'), nullable=False, comment='quadrant digits 0-3 from the root'),
    sa.Column('min_x', sa.Double(), nullable=False, comment='UTM 45N metres'),
    sa.Column('min_y', sa.Double(), nullable=False),
    sa.Column('max_x', sa.Double(), nullable=False),
    sa.Column('max_y', sa.Double(), nullable=False),
    sa.CheckConstraint("quadkey ~ '^[0-3]*$'", name=op.f('ck_parcel_quadkeys_quadkey_digits')),
    sa.CheckConstraint('min_x <= max_x AND min_y <= max_y', name=op.f('ck_parcel_quadkeys_bbox_order')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_parcel_quadkeys_parcel_id_parcels'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('parcel_id', name=op.f('pk_parcel_quadkeys'))
    )
    op.create_index(op.f('ix_parcel_quadkeys_quadkey'), 'parcel_quadkeys', ['quadkey'], unique=False)
    op.create_table('transactions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('case_id', sa.String(length=20), nullable=False, comment='CaseID, unique across the system'),
    sa.Column('txn_type', sa.String(length=30), nullable=False),
    sa.Column('parcel_id', sa.Integer(), nullable=True, comment='parcel concerned; the parent for a split'),
    sa.Column('status', sa.String(length=10), server_default=sa.text("'draft'"), nullable=False),
    sa.Column('deed_ref', sa.String(length=40), nullable=True),
    sa.Column('deed_date', sa.Date(), nullable=True),
    sa.Column('office', sa.String(length=100), nullable=True),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("case_id ~ '^[0-9]{6,20}$'", name=op.f('ck_transactions_case_id_format')),
    sa.CheckConstraint("status IN ('draft', 'approved', 'rejected')", name=op.f('ck_transactions_status')),
    sa.CheckConstraint("txn_type IN ('registration', 'boundary_update', 'split', 'merge', 'rajinama', 'hal_ko_bakaspatra', 'danpatra', 'chhod_patra', 'ansha_banda', 'namasari', 'samsodhan', 'rokka', 'fukuwa')", name=op.f('ck_transactions_txn_type')),
    sa.ForeignKeyConstraint(['created_by'], ['officers.id'], name=op.f('fk_transactions_created_by_officers')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_transactions_parcel_id_parcels')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_transactions')),
    sa.UniqueConstraint('case_id', name=op.f('uq_transactions_case_id'))
    )
    op.create_index(op.f('ix_transactions_parcel_id'), 'transactions', ['parcel_id'], unique=False)
    op.create_table('audit_log',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('officer_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=40), nullable=False, comment='e.g. parcel_registered, boundary_updated, ownership_transferred'),
    sa.Column('parcel_id', sa.Integer(), nullable=True),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['officer_id'], ['officers.id'], name=op.f('fk_audit_log_officer_id_officers')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_audit_log_parcel_id_parcels')),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], name=op.f('fk_audit_log_transaction_id_transactions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_log'))
    )
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_log_parcel_id'), 'audit_log', ['parcel_id'], unique=False)
    op.create_table('parcel_geometry_history',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parcel_id', sa.Integer(), nullable=False),
    sa.Column('boundary', Geometry(geometry_type='POLYGON', srid=4326, dimension=2, spatial_index=False, from_text='ST_GeomFromEWKT', name='geometry', nullable=False), nullable=False),
    sa.Column('area_m2', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('valid_from', sa.DateTime(timezone=True), nullable=False),
    sa.Column('valid_to', sa.DateTime(timezone=True), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('area_m2 > 0', name=op.f('ck_parcel_geometry_history_area_m2')),
    sa.CheckConstraint('valid_to >= valid_from', name=op.f('ck_parcel_geometry_history_valid_period')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_parcel_geometry_history_parcel_id_parcels')),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], name=op.f('fk_parcel_geometry_history_transaction_id_transactions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parcel_geometry_history'))
    )
    op.create_index(op.f('ix_parcel_geometry_history_parcel_id'), 'parcel_geometry_history', ['parcel_id'], unique=False)
    op.create_table('parcel_lineage',
    sa.Column('parent_id', sa.Integer(), nullable=False),
    sa.Column('child_id', sa.Integer(), nullable=False),
    sa.Column('transaction_id', sa.Integer(), nullable=False),
    sa.CheckConstraint('parent_id <> child_id', name=op.f('ck_parcel_lineage_not_self')),
    sa.ForeignKeyConstraint(['child_id'], ['parcels.id'], name=op.f('fk_parcel_lineage_child_id_parcels')),
    sa.ForeignKeyConstraint(['parent_id'], ['parcels.id'], name=op.f('fk_parcel_lineage_parent_id_parcels')),
    sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id'], name=op.f('fk_parcel_lineage_transaction_id_transactions')),
    sa.PrimaryKeyConstraint('parent_id', 'child_id', name=op.f('pk_parcel_lineage'))
    )
    op.create_index(op.f('ix_parcel_lineage_child_id'), 'parcel_lineage', ['child_id'], unique=False)
    op.create_table('parcel_ownership',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parcel_id', sa.Integer(), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('share_num', sa.Integer(), nullable=False),
    sa.Column('share_den', sa.Integer(), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_to', sa.Date(), nullable=True, comment='NULL = current owner'),
    sa.Column('acquired_txn_id', sa.Integer(), nullable=True),
    sa.Column('ended_txn_id', sa.Integer(), nullable=True),
    sa.CheckConstraint('share_num > 0 AND share_den > 0 AND share_num <= share_den', name=op.f('ck_parcel_ownership_share')),
    sa.CheckConstraint('valid_to IS NULL OR valid_to >= valid_from', name=op.f('ck_parcel_ownership_valid_period')),
    sa.ForeignKeyConstraint(['acquired_txn_id'], ['transactions.id'], name=op.f('fk_parcel_ownership_acquired_txn_id_transactions')),
    sa.ForeignKeyConstraint(['ended_txn_id'], ['transactions.id'], name=op.f('fk_parcel_ownership_ended_txn_id_transactions')),
    sa.ForeignKeyConstraint(['owner_id'], ['owners.id'], name=op.f('fk_parcel_ownership_owner_id_owners')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_parcel_ownership_parcel_id_parcels')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_parcel_ownership'))
    )
    op.create_index(op.f('ix_parcel_ownership_owner_id'), 'parcel_ownership', ['owner_id'], unique=False)
    op.create_index('ix_parcel_ownership_parcel_id', 'parcel_ownership', ['parcel_id'], unique=False)
    op.create_index('uq_parcel_ownership_current', 'parcel_ownership', ['parcel_id', 'owner_id'], unique=True, postgresql_where=sa.text('valid_to IS NULL'))
    op.create_table('rokka',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('parcel_id', sa.Integer(), nullable=False),
    sa.Column('requested_by_type', sa.String(length=20), nullable=False),
    sa.Column('requested_by_name', sa.String(length=150), nullable=False),
    sa.Column('reason', sa.Text(), nullable=True),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('fukuwa_date', sa.Date(), nullable=True, comment='NULL = still active'),
    sa.Column('placed_txn_id', sa.Integer(), nullable=True),
    sa.Column('released_txn_id', sa.Integer(), nullable=True),
    sa.CheckConstraint("requested_by_type IN ('bank', 'court', 'ciaa', 'government', 'other')", name=op.f('ck_rokka_requested_by_type')),
    sa.CheckConstraint('fukuwa_date IS NULL OR fukuwa_date >= start_date', name=op.f('ck_rokka_valid_period')),
    sa.ForeignKeyConstraint(['parcel_id'], ['parcels.id'], name=op.f('fk_rokka_parcel_id_parcels')),
    sa.ForeignKeyConstraint(['placed_txn_id'], ['transactions.id'], name=op.f('fk_rokka_placed_txn_id_transactions')),
    sa.ForeignKeyConstraint(['released_txn_id'], ['transactions.id'], name=op.f('fk_rokka_released_txn_id_transactions')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rokka'))
    )
    op.create_index(op.f('ix_rokka_parcel_id'), 'rokka', ['parcel_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_rokka_parcel_id'), table_name='rokka')
    op.drop_table('rokka')
    op.drop_index(op.f('ix_parcel_ownership_owner_id'), table_name='parcel_ownership')
    op.drop_index('ix_parcel_ownership_parcel_id', table_name='parcel_ownership')
    op.drop_index('uq_parcel_ownership_current', table_name='parcel_ownership', postgresql_where=sa.text('valid_to IS NULL'))
    op.drop_table('parcel_ownership')
    op.drop_index(op.f('ix_parcel_lineage_child_id'), table_name='parcel_lineage')
    op.drop_table('parcel_lineage')
    op.drop_index(op.f('ix_parcel_geometry_history_parcel_id'), table_name='parcel_geometry_history')
    op.drop_table('parcel_geometry_history')
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_index(op.f('ix_audit_log_parcel_id'), table_name='audit_log')
    op.drop_table('audit_log')
    op.drop_index(op.f('ix_transactions_parcel_id'), table_name='transactions')
    op.drop_table('transactions')
    op.drop_index(op.f('ix_parcel_quadkeys_quadkey'), table_name='parcel_quadkeys')
    op.drop_table('parcel_quadkeys')
    op.drop_index(op.f('ix_parcel_issues_parcel_id'), table_name='parcel_issues')
    op.drop_table('parcel_issues')
    op.drop_table('setback_rules')
    op.drop_table('places')
    op.drop_table('parcels')
    op.drop_table('owners')
    op.drop_table('officers')
    op.drop_table('features')
    # The postgis extension is left installed; other database objects may use it.
