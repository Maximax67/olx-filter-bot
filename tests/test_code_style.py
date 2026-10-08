import ast
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ("src", "tests", "migrations")
PYTHON_FILES = sorted(path for folder in FOLDERS for path in (ROOT / folder).rglob("*.py"))


def label(path: Path) -> str:
    return str(path.relative_to(ROOT))


@pytest.mark.parametrize("path", PYTHON_FILES, ids=label)
def test_file_contains_no_comments(path: Path) -> None:
    with path.open("rb") as handle:
        comments = [
            f"line {token.start[0]}: {token.string}"
            for token in tokenize.tokenize(handle.readline)
            if token.type == tokenize.COMMENT
        ]
    assert comments == []


@pytest.mark.parametrize("path", PYTHON_FILES, ids=label)
def test_file_contains_no_docstrings(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    documented = [
        getattr(node, "name", "<module>")
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and ast.get_docstring(node) is not None
    ]
    assert documented == []
