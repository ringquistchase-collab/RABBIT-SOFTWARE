#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys
from pathlib import Path

REQUIREMENTS = [
    "fastapi",
    "uvicorn[standard]",
    "httpx",
    "pydantic",
]

COORDINATOR_ENV = """\
FEDERATION_DB=federation.db
COORDINATOR_API_KEY=change-me
SIGNING_SECRET=change-me-too
COORDINATOR_HOST=127.0.0.1
COORDINATOR_PORT=8100
"""

NODE_ENV = """\
NODE_API_KEY=node-secret
NODE_ID=node-1
NODE_NAME=Example Node
NODE_HOST=127.0.0.1
NODE_PORT=8200
"""


def run(cmd, cwd=None):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, cwd=cwd, check=True)


def ensure_venv(project_dir: Path) -> Path:
    venv_dir = project_dir / ".venv"
    if not venv_dir.exists():
        run([sys.executable, "-m", "venv", str(venv_dir)])
    python_bin = venv_dir / "bin" / "python"
    pip_bin = venv_dir / "bin" / "pip"
    run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    run([str(pip_bin), "install", *REQUIREMENTS])
    return python_bin


def write_if_missing(path: Path, content: str):
    if not path.exists():
        path.write_text(content, encoding="utf-8")
        print(f"Wrote {path}")
    else:
        print(f"Exists: {path}")


def main():
    parser = argparse.ArgumentParser(description="Deploy federated LLM corpus services")
    parser.add_argument("--project-dir", default=".")
    parser.add_argument("--role", choices=["coordinator", "node"], required=True)
    parser.add_argument("--run", action="store_true", help="Run service after setup")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    python_bin = ensure_venv(project_dir)

    if args.role == "coordinator":
        write_if_missing(project_dir / ".env.coordinator", COORDINATOR_ENV)
        print("Coordinator env file: .env.coordinator")
        if args.run:
            env = os.environ.copy()
            env.update(
                {
                    "FEDERATION_DB": "federation.db",
                    "COORDINATOR_API_KEY": "change-me",
                    "SIGNING_SECRET": "change-me-too",
                }
            )
            run(
                [
                    str(python_bin),
                    "-m",
                    "uvicorn",
                    "coordinator_backend:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8100",
                    "--reload",
                ],
                cwd=project_dir,
            )

    elif args.role == "node":
        write_if_missing(project_dir / ".env.node", NODE_ENV)
        print("Node env file: .env.node")
        if args.run:
            env = os.environ.copy()
            env.update(
                {
                    "NODE_API_KEY": "node-secret",
                    "NODE_ID": "node-1",
                    "NODE_NAME": "Example Node",
                }
            )
            run(
                [
                    str(python_bin),
                    "-m",
                    "uvicorn",
                    "node_backend:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8200",
                    "--reload",
                ],
                cwd=project_dir,
            )

    print("\nSetup complete.")
    print("\nManual run examples:")
    print(f"  {python_bin} -m uvicorn coordinator_backend:app --host 127.0.0.