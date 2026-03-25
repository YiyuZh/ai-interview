"""add_position_knowledge_base

Revision ID: 8d5e6b7a9f21
Revises: c7f982abaaf0
Create Date: 2026-03-24 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8d5e6b7a9f21'
down_revision: Union[str, None] = 'c7f982abaaf0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'position_knowledge_bases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('target_position', sa.String(length=255), nullable=False),
        sa.Column('knowledge_content', sa.Text(), nullable=False),
        sa.Column('focus_points', sa.Text(), nullable=True),
        sa.Column('interviewer_prompt', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_position_knowledge_bases_id'), 'position_knowledge_bases', ['id'], unique=False)
    op.create_index(op.f('ix_position_knowledge_bases_user_id'), 'position_knowledge_bases', ['user_id'], unique=False)
    op.create_index(op.f('ix_position_knowledge_bases_target_position'), 'position_knowledge_bases', ['target_position'], unique=False)

    op.add_column('interviews', sa.Column('knowledge_base_id', sa.Integer(), nullable=True))
    op.add_column('interviews', sa.Column('knowledge_base_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key(
        'fk_interviews_knowledge_base_id_position_knowledge_bases',
        'interviews',
        'position_knowledge_bases',
        ['knowledge_base_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_interviews_knowledge_base_id_position_knowledge_bases', 'interviews', type_='foreignkey')
    op.drop_column('interviews', 'knowledge_base_snapshot')
    op.drop_column('interviews', 'knowledge_base_id')

    op.drop_index(op.f('ix_position_knowledge_bases_target_position'), table_name='position_knowledge_bases')
    op.drop_index(op.f('ix_position_knowledge_bases_user_id'), table_name='position_knowledge_bases')
    op.drop_index(op.f('ix_position_knowledge_bases_id'), table_name='position_knowledge_bases')
    op.drop_table('position_knowledge_bases')
