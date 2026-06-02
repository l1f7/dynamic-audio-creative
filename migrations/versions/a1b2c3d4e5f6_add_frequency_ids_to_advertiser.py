"""Add Frequency credentials to Advertiser; add vast_response to AdRun

Revision ID: a1b2c3d4e5f6
Revises: 4cc4e71b7ae6
Create Date: 2026-06-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '4cc4e71b7ae6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_client', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('frequency_token', sa.String(length=200), nullable=True))

    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vast_response', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.drop_column('vast_response')

    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.drop_column('frequency_token')
        batch_op.drop_column('frequency_client')
