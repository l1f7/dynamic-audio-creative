"""Add desktop push mode: api_keys table and pushed-run provenance

Revision ID: b9c0d1e2f3a4
Revises: c4d5e6f7a8b9
Create Date: 2026-09-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b9c0d1e2f3a4'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('advertiser_id', sa.Integer(), sa.ForeignKey('advertisers.id'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('key_prefix', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_api_keys_advertiser_id', 'api_keys', ['advertiser_id'])
    op.create_index('ix_api_keys_key_prefix', 'api_keys', ['key_prefix'])

    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_filename', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('source_content_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('source_bytes', sa.BigInteger(), nullable=True))
        batch_op.create_index('ix_ad_runs_source_content_hash', ['source_content_hash'], unique=False)
        batch_op.create_unique_constraint(
            'uq_ad_runs_campaign_content_hash', ['campaign_id', 'source_content_hash']
        )


def downgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.drop_constraint('uq_ad_runs_campaign_content_hash', type_='unique')
        batch_op.drop_index('ix_ad_runs_source_content_hash')
        batch_op.drop_column('source_bytes')
        batch_op.drop_column('source_content_hash')
        batch_op.drop_column('source_filename')

    op.drop_index('ix_api_keys_key_prefix', table_name='api_keys')
    op.drop_index('ix_api_keys_advertiser_id', table_name='api_keys')
    op.drop_table('api_keys')
