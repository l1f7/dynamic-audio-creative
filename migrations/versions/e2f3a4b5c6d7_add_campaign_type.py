"""Add campaign_type to Campaign

Existing campaigns are all 'automated' — that is the behaviour they have
today. Campaigns that already received a pushed file are backfilled to
'push' so the desktop daemon keeps seeing them after this deploy.

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e2f3a4b5c6d7'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'campaign_type',
                sa.String(length=20),
                nullable=False,
                server_default='automated',
            )
        )

    op.execute(
        """
        UPDATE campaigns
           SET campaign_type = 'push'
         WHERE id IN (
               SELECT DISTINCT campaign_id
                 FROM ad_runs
                WHERE triggered_by = 'watcher'
         )
        """
    )


def downgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('campaign_type')
