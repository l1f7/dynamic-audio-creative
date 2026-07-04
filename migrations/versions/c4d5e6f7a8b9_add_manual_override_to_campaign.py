"""Add manual override script fields to campaign and ad_run

Revision ID: c4d5e6f7a8b9
Revises: b1c2d3e4f5a6
Create Date: 2026-07-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c4d5e6f7a8b9'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('manual_override_script', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('use_manual_override', sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('script_source', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.drop_column('script_source')

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('use_manual_override')
        batch_op.drop_column('manual_override_script')
