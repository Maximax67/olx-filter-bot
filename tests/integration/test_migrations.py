import os
import subprocess
import sys

from tests.conftest import ROOT


def test_models_and_migrations_are_in_sync(migrated_database: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": migrated_database},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
