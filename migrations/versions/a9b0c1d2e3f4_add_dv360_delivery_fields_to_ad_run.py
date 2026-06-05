"""Add DV360 delivery fields to ad_runs

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a9b0c1d2e3f4'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_delivered_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('dv360_creative_name', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('dv360_delivery_error', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.drop_column('dv360_delivery_error')
        batch_op.drop_column('dv360_creative_name')
        batch_op.drop_column('dv360_delivered_at')
