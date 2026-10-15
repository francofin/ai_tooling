"""The image is built by `cdk deploy` on Franc's machine, so these tests guard
what can be checked without Docker: the build context and what it copies."""
import ast
import sys
from pathlib import Path

PIPELINES = Path(__file__).resolve().parents[1]
STDLIB = set(sys.stdlib_module_names)
# import name → requirements.txt name
DISTRIBUTIONS = {"dotenv": "python-dotenv", "pandas_market_calendars": "pandas-market-calendars",
                 "botocore": "boto3", "pyarrow": "pyarrow"}


def test_dockerfile_copies_from_its_own_folder():
    text = (PIPELINES / "Dockerfile").read_text()
    for line in text.splitlines():
        if line.startswith("COPY "):
            source = line.split()[1]
            assert (PIPELINES / source).exists(), source
    assert 'ENTRYPOINT ["python", "-m", "pipelines"]' in text


def test_dockerignore_keeps_tests_out():
    lines = (PIPELINES / ".dockerignore").read_text().split()
    assert "tests/" in lines and "**/__pycache__" in lines


def test_runtime_imports_are_in_requirements():
    required = {line.split("==")[0].strip().lower()
                for line in (PIPELINES / "requirements.txt").read_text().splitlines()
                if line and not line.startswith("#")}
    for path in PIPELINES.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top in STDLIB or top == "pipelines":
                    continue
                dist = DISTRIBUTIONS.get(top, top).lower()
                assert dist in required, f"{path.name} imports {top}, not in requirements.txt"
