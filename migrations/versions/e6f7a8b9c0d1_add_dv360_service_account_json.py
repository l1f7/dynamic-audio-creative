"""Add dv360_service_account_json to Advertiser

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-05 00:00:00.000000

NOTE: This revision duplicated d4e5f6a7b8c9, which already adds
advertisers.dv360_service_account_json. Databases migrated before this
was made a no-op already have the revision recorded, so Alembic skips
it; on a fresh database the original body crashed with "duplicate
column name". Kept as a no-op to preserve the revision chain.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # No-op: d4e5f6a7b8c9 already added this column.
    pass


def downgrade():
    # No-op: the column is dropped by d4e5f6a7b8c9's downgrade.
    pass
