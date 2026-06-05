"""Add dv360_service_account_json to Advertiser

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-06-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e6f7a8b9c0d1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('dv360_service_account_json', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.drop_column('dv360_service_account_json')
