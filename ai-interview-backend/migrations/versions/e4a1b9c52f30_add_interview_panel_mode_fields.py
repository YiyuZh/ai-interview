"""add_interview_panel_mode_fields

Revision ID: e4a1b9c52f30
Revises: c3f8a6b1d201
Create Date: 2026-03-25 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "e4a1b9c52f30"
down_revision: Union[str, None] = "c3f8a6b1d201"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("interview_mode", sa.String(length=20), nullable=False, server_default="single"),
    )
    op.add_column(
        "interviews",
        sa.Column("panel_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(op.f("ix_interviews_interview_mode"), "interviews", ["interview_mode"], unique=False)
    op.execute("UPDATE interviews SET interview_mode = 'single' WHERE interview_mode IS NULL")


def downgrade() -> None:
    op.drop_index(op.f("ix_interviews_interview_mode"), table_name="interviews")
    op.drop_column("interviews", "panel_snapshot")
    op.drop_column("interviews", "interview_mode")
