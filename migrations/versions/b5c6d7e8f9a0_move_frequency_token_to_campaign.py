"""Move frequency_token from advertisers to campaigns

A Frequency token identifies a single ad unit, so one advertiser running
several campaigns needs one token per campaign. Each existing campaign
inherits its advertiser's token so nothing stops delivering.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-09-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b5c6d7e8f9a0'
down_revision = 'a4b5c6d7e8f9'
branch_labels = None
depends_on = None


COPY_TOKENS_TO_CAMPAIGNS = """
    UPDATE campaigns
    SET frequency_token = (
        SELECT frequency_token FROM advertisers
        WHERE advertisers.id = campaigns.advertiser_id
    )
"""

# Restores one token per advertiser; the first campaign's wins.
COPY_TOKENS_TO_ADVERTISERS = """
    UPDATE advertisers
    SET frequency_token = (
        SELECT frequency_token FROM campaigns
        WHERE campaigns.advertiser_id = advertisers.id
          AND campaigns.frequency_token IS NOT NULL
        ORDER BY campaigns.id
        LIMIT 1
    )
"""


def upgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_token', sa.Text(), nullable=True))

    op.execute(COPY_TOKENS_TO_CAMPAIGNS)

    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.drop_column('frequency_token')


def downgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_token', sa.Text(), nullable=True))

    op.execute(COPY_TOKENS_TO_ADVERTISERS)

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('frequency_token')
