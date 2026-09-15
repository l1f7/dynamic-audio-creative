"""Merge dv360 partner/campaign/io id branch with push mode branch

Both branches diverged from f7a8b9c0d1e2 and touch disjoint tables
(advertisers/campaigns vs api_keys/ad_runs), so this is an empty merge.

Revision ID: d1e2f3a4b5c6
Revises: a8b9c0d1e2f3, b9c0d1e2f3a4
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd1e2f3a4b5c6'
down_revision = ('a8b9c0d1e2f3', 'b9c0d1e2f3a4')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
