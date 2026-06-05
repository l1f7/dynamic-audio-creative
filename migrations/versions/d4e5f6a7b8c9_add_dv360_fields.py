"""Add DV360 fields to Advertiser and Campaign

Revision ID: d4e5f6a7b8c9
Revises: f6a7b8c9d0e1
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_advertiser_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('dv360_service_account_json', sa.Text(), nullable=True))

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('dv360_enabled')

    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.drop_column('dv360_service_account_json')
        batch_op.drop_column('dv360_advertiser_id')
