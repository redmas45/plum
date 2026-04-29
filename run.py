#!/usr/bin/env python3
"""
Local runner script for Plum Claims Processing System.
Automatically sets up the environment and starts the server.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main():
    host = "127.0.0.1"
    port = 8000
    reload = True

    project_root = Path(__file__).parent.absolute()
    
    # Check for .env file
    env_file = project_root / ".env"
    if not env_file.exists():
        print("Warning: .env file not found!")
        print("Creating from .env.example...")
        example = project_root / ".env.example"
        if example.exists():
            import shutil
            shutil.copy(example, env_file)
            print("Success: Created .env file. Please edit it to add your GROQ_API_KEY before running claims.")
        else:
            print("Error: .env.example not found. Please create a .env file with GROQ_API_KEY.")

    print(f"Starting Plum Claims API on http://{host}:{port}")
    print(f"Dashboard available at http://{host}:{port}/")
    print("-" * 50)

    # Run uvicorn
    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]
    
    if reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd, cwd=project_root)
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    main()
