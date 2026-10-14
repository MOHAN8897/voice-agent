"""Keep Alembic revision IDs within its version table's default column width."""
import ast
from pathlib import Path


def test_migration_revision_ids_fit_alembic_version_column():
    versions_dir = Path(__file__).resolve().parents[1] / "db" / "migrations" / "versions"
    revisions = []
    for migration in versions_dir.glob("*.py"):
        module = ast.parse(migration.read_text(encoding="utf-8"))
        revision = next(
            (
                statement.value.value
                for statement in module.body
                if isinstance(statement, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "revision"
                    for target in statement.targets
                )
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ),
            None,
        )
        if revision:
            revisions.append((migration.name, revision))

    assert revisions
    assert all(len(revision) <= 32 for _, revision in revisions), [
        (filename, revision, len(revision))
        for filename, revision in revisions
        if len(revision) > 32
    ]
