"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from typing import Sequence, Union
# Runtime: Typing helpers for type hints.
# Architecture: Used for type safety in migration definitions.
# Summary: Imports typing utilities.

from alembic import op
# Runtime: Alembic's op object for migrations.
# Architecture: Provides context for operations like create_table.
# Summary: Imports Alembic operations.

import sqlalchemy as sa
# Runtime: SQLAlchemy core library for table definitions.
# Architecture: Provides column types and schema constructs.
# Summary: Imports SQLAlchemy.

${imports if imports else ""}
# Runtime: Additional imports may be injected here.
# Architecture: Allows migration to include extra modules.
# Summary: Keeps placeholder for optional imports.

# revision identifiers, used by Alembic.
# Runtime: Set unique ID for this migration.
# Architecture: Alembic tracks order via revision and down_revision.
# Summary: Declares migration identifiers.
revision: str = ${repr(up_revision)}
# Runtime: Indicates the previous migration(s) this one depends on.
# Architecture: Supports branching migrations.
# Summary: Defines dependencies.
# Note: Can be a single string, sequence, or None.
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
# Runtime: Optional label(s) for this migration.
# Architecture: Enables grouping migrations.
# Summary: Branch labels.
bundle_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
# Runtime: Dependencies beyond the direct next revision.
# Architecture: Allows specifying unrelated migrations that must run first.
# Summary: Depends on.
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    # Runtime: Called when migrating forward.
    # Architecture: Contains migration logic defined by developer.
    # Summary: Executes 'up' changes.
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    # Runtime: Called when rolling back.
    # Architecture: Reverts the changes made in upgrade.
    # Summary: Executes 'down' changes.
    ${downgrades if downgrades else "pass"}
