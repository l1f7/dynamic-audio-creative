"""Move per-target delivery results into a delivery_attempts table

Delivery lived in seven columns on ad_runs, split by target. That meant a new
ad server needed three more columns and a hand-wired branch at every call site,
and a redelivery overwrote the previous result so history was lost.

The backfill reads each run's existing columns into at most two attempt rows,
so nothing already recorded is dropped. attempted_at falls back to the run's
completed_at (then created_at) when a target only ever recorded an error, since
the old schema stored no timestamp for failures.

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-09-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a4b5c6d7e8f9'
down_revision = 'f3a4b5c6d7e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'delivery_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ad_run_id', sa.Integer(), nullable=False),
        sa.Column('target', sa.String(length=50), nullable=False),
        sa.Column('succeeded', sa.Boolean(), nullable=False),
        sa.Column('reference', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('attempted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['ad_run_id'], ['ad_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_delivery_attempts_ad_run_id', 'delivery_attempts', ['ad_run_id'])

    # Frequency: a success carries delivered_at and the VAST response.
    op.execute("""
        INSERT INTO delivery_attempts
               (ad_run_id, target, succeeded, reference, error, attempted_at)
        SELECT id, 'frequency', TRUE, vast_response, NULL, delivered_at
          FROM ad_runs
         WHERE delivered_at IS NOT NULL AND delivery_error IS NULL
    """)
    op.execute("""
        INSERT INTO delivery_attempts
               (ad_run_id, target, succeeded, reference, error, attempted_at)
        SELECT id, 'frequency', FALSE, NULL, delivery_error,
               COALESCE(delivered_at, completed_at, created_at)
          FROM ad_runs
         WHERE delivery_error IS NOT NULL
    """)

    # DV360: a success carries dv360_delivered_at and the creative name.
    op.execute("""
        INSERT INTO delivery_attempts
               (ad_run_id, target, succeeded, reference, error, attempted_at)
        SELECT id, 'dv360', TRUE, dv360_creative_name, NULL, dv360_delivered_at
          FROM ad_runs
         WHERE dv360_delivered_at IS NOT NULL AND dv360_delivery_error IS NULL
    """)
    op.execute("""
        INSERT INTO delivery_attempts
               (ad_run_id, target, succeeded, reference, error, attempted_at)
        SELECT id, 'dv360', FALSE, NULL, dv360_delivery_error,
               COALESCE(dv360_delivered_at, completed_at, created_at)
          FROM ad_runs
         WHERE dv360_delivery_error IS NOT NULL
    """)

    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.drop_column('delivered_at')
        batch_op.drop_column('delivery_reference')
        batch_op.drop_column('delivery_error')
        batch_op.drop_column('vast_response')
        batch_op.drop_column('dv360_delivered_at')
        batch_op.drop_column('dv360_creative_name')
        batch_op.drop_column('dv360_delivery_error')


def downgrade():
    with op.batch_alter_table('ad_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('delivered_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('delivery_reference', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('delivery_error', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('vast_response', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('dv360_delivered_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('dv360_creative_name', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('dv360_delivery_error', sa.Text(), nullable=True))

    # Collapse the history back to the latest attempt per target.
    for target, ok_time, ok_ref, err_col in (
        ('frequency', 'delivered_at', 'vast_response', 'delivery_error'),
        ('dv360', 'dv360_delivered_at', 'dv360_creative_name', 'dv360_delivery_error'),
    ):
        op.execute(f"""
            UPDATE ad_runs SET
                {ok_time} = latest.attempted_at_if_ok,
                {ok_ref}  = latest.reference_if_ok,
                {err_col} = latest.error_if_failed
            FROM (
                SELECT DISTINCT ON (ad_run_id) ad_run_id,
                       CASE WHEN succeeded THEN attempted_at END AS attempted_at_if_ok,
                       CASE WHEN succeeded THEN reference END    AS reference_if_ok,
                       CASE WHEN NOT succeeded THEN error END    AS error_if_failed
                  FROM delivery_attempts
                 WHERE target = '{target}'
                 ORDER BY ad_run_id, attempted_at DESC
            ) AS latest
            WHERE ad_runs.id = latest.ad_run_id
        """)

    op.execute("UPDATE ad_runs SET delivery_reference = 'frequency' WHERE delivered_at IS NOT NULL")

    op.drop_index('ix_delivery_attempts_ad_run_id', table_name='delivery_attempts')
    op.drop_table('delivery_attempts')
