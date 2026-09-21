"""Support multiple Frequency tags per campaign

A campaign may need to deliver to more than one Frequency ad unit, so
frequency_app_id/frequency_token (one pair) become frequency_tags — a JSON
list of {"token": ..., "app_id": ...} pairs. Existing campaigns keep their
one pair as a single-item list.

Revision ID: d2e3f4a5b6c7
Revises: c6d7e8f9a0b1
Create Date: 2026-09-21 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2e3f4a5b6c7'
down_revision = 'c6d7e8f9a0b1'
branch_labels = None
depends_on = None


campaigns = sa.table(
    'campaigns',
    sa.column('id', sa.Integer),
    sa.column('frequency_app_id', sa.String),
    sa.column('frequency_token', sa.Text),
    sa.column('frequency_tags', sa.JSON),
)


def upgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_tags', sa.JSON(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.select(campaigns.c.id, campaigns.c.frequency_app_id, campaigns.c.frequency_token)
        .where(campaigns.c.frequency_token.isnot(None))
    ).fetchall()
    for row in rows:
        tags = [{"token": row.frequency_token, "app_id": row.frequency_app_id}]
        bind.execute(campaigns.update().where(campaigns.c.id == row.id).values(frequency_tags=tags))

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('frequency_app_id')
        batch_op.drop_column('frequency_token')


def downgrade():
    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_app_id', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('frequency_token', sa.Text(), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(
        sa.select(campaigns.c.id, campaigns.c.frequency_tags)
        .where(campaigns.c.frequency_tags.isnot(None))
    ).fetchall()
    for row in rows:
        tags = row.frequency_tags or []
        if not tags:
            continue
        first = tags[0]
        bind.execute(
            campaigns.update().where(campaigns.c.id == row.id).values(
                frequency_app_id=first.get("app_id"),
                frequency_token=first.get("token"),
            )
        )

    with op.batch_alter_table('campaigns', schema=None) as batch_op:
        batch_op.drop_column('frequency_tags')
