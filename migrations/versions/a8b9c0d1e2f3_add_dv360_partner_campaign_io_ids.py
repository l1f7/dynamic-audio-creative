"""Add dv360_partner_id to Advertiser and dv360_campaign_id/dv360_insertion_order_id to Campaign

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-06-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8b9c0d1e2f3'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_partner_id', sa.String(length=100), nullable=True))

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_campaign_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('dv360_insertion_order_id', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('dv360_insertion_order_id')
        batch_op.drop_column('dv360_campaign_id')

    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.drop_column('dv360_partner_id')
