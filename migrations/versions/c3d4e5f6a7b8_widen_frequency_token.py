"""Widen frequency_token to Text

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.alter_column('frequency_token',
                              existing_type=sa.String(length=200),
                              type_=sa.Text(),
                              existing_nullable=True)


def downgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.alter_column('frequency_token',
                              existing_type=sa.Text(),
                              type_=sa.String(length=200),
                              existing_nullable=True)
