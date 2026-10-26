"""Bind a long-lived "Keep me signed in" policy to a refresh-token family.

Revision ID: 046_remember_me_sessions
Revises: 045_technical_fallback
Create Date: 2026-10-26
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "046_remember_me_sessions"
down_revision: str | None = "045_technical_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column(
            "remember_me",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("refresh_tokens", "remember_me")
