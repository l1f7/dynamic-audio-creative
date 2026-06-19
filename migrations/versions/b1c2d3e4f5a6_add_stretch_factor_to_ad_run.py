"""Add stretch_factor to ad_runs

Revision ID: b1c2d3e4f5a6
Revises: a9b0c1d2e3f4
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b1c2d3e4f5a6'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stretch_factor', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.drop_column('stretch_factor')
