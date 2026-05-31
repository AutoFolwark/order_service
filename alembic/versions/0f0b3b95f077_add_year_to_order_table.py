"""add year to order table

Revision ID: 0f0b3b95f077
Revises: 3114a3df5746
Create Date: 2026-05-31 18:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0f0b3b95f077"
down_revision: Union[str, Sequence[str], None] = "3114a3df5746"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("order", sa.Column("year", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("order", "year")
