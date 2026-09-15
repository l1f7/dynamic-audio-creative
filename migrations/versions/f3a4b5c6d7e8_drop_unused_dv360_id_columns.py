"""Drop the unused DV360 partner/campaign/insertion-order columns

Added by a8b9c0d1e2f3 but never declared on any model and never read by any
code path. DV360 creative upload is advertiser-scoped (app/delivery/dv360.py),
so it needs dv360_advertiser_id and dv360_line_item_id only. Dropping them so
the schema stops implying a capability the app does not have.

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f3a4b5c6d7e8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('dv360_insertion_order_id')
        batch_op.drop_column('dv360_campaign_id')

    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.drop_column('dv360_partner_id')


def downgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_partner_id', sa.String(length=100), nullable=True))

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_campaign_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('dv360_insertion_order_id', sa.String(length=100), nullable=True))
