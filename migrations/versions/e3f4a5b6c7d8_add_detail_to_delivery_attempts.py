"""Add detail to delivery_attempts

A Frequency delivery can now fan out to several tags in one attempt round,
so each row needs to say which one it was for.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-21 00:00:00.000001

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('delivery_attempts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('detail', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('delivery_attempts', schema=None) as batch_op:
        batch_op.drop_column('detail')
