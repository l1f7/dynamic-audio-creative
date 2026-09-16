"""Move DV360 credentials from advertisers to campaigns

An advertiser is a container for campaigns. A DV360 service account is scoped
to one advertiser account inside DV360, so it belongs to the campaign that
delivers through it, beside the line item. Each existing campaign inherits its
advertiser's values so nothing stops delivering.

This is a separate revision from b5c6d7e8f9a0 (the Frequency token move)
because that one had already run in production before the DV360 move was
written. Alembic never re-runs an applied revision, so extending it in place
left production without these columns.

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-09-16 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c6d7e8f9a0b1'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


MOVED_COLUMNS = (
    ('dv360_advertiser_id', sa.String(length=100)),
    ('dv360_service_account_json', sa.Text()),
)

COPY_TO_CAMPAIGNS = """
    UPDATE campaigns
    SET {column} = (
        SELECT {column} FROM advertisers
        WHERE advertisers.id = campaigns.advertiser_id
    )
"""

# Restores one value per advertiser; the lowest-id campaign that has one wins.
COPY_TO_ADVERTISERS = """
    UPDATE advertisers
    SET {column} = (
        SELECT {column} FROM campaigns
        WHERE campaigns.advertiser_id = advertisers.id
          AND campaigns.{column} IS NOT NULL
        ORDER BY campaigns.id
        LIMIT 1
    )
"""


def upgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        for name, column_type in MOVED_COLUMNS:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))

    for name, _ in MOVED_COLUMNS:
        op.execute(COPY_TO_CAMPAIGNS.format(column=name))

    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        for name, _ in MOVED_COLUMNS:
            batch_op.drop_column(name)


def downgrade():
    with op.batch_alter_table('advertisers', schema=None) as batch_op:
        for name, column_type in MOVED_COLUMNS:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))

    for name, _ in MOVED_COLUMNS:
        op.execute(COPY_TO_ADVERTISERS.format(column=name))

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        for name, _ in MOVED_COLUMNS:
            batch_op.drop_column(name)
