"""
Unified Runner for Maritime Operations Assistant.
Launches all system services in one command:
  1. FastMCP Knowledge Graph Server (Port 8000)
  2. Maritime Operations AI Agent API (Port 8080)
  3. Frontend React / Vite Web Interface (Port 5173)
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

# Resolve Python interpreter (prefer local .venv if present)
PYTHON_EXE = sys.executable
VENV_PYTHON = ROOT_DIR / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
if VENV_PYTHON.exists():
    PYTHON_EXE = str(VENV_PYTHON)

processes = []


def kill_process_tree(proc):
    """Terminates a process and any spawned child subprocesses."""
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            proc.terminate()
            proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def shutdown_all(*args):
    """Graceful shutdown handler for Ctrl+C."""
    print("\n" + "=" * 68)
    print("  Shutting down all Maritime Operations Assistant services...")
    print("=" * 68)
    for p in processes:
        kill_process_tree(p)
    print("  All services stopped cleanly.\n")
    sys.exit(0)


def check_neo4j():
    """Probes Neo4j connectivity and displays status."""
    try:
        from knowledge_graph.database import Neo4jClient
        client = Neo4jClient()
        res = client.execute_read_query("RETURN 1 AS ping")
        if res:
            print("  [OK] Neo4j Knowledge Graph connected at bolt://localhost:7687")
            return True
    except Exception as exc:
        print("  [INFO] Neo4j database not reachable yet on localhost:7687.")
        print("         (Start Neo4j Desktop or Docker container to enable live graph data.)")
        return False


def main():
    parser = argparse.ArgumentParser(description="Maritime Operations Assistant Unified Runner")
    parser.add_argument("--port-api", type=int, default=8080, help="Port for AI Agent FastAPI server (default: 8080)")
    parser.add_argument("--port-mcp", type=int, default=8000, help="Port for FastMCP Knowledge Graph server (default: 8000)")
    parser.add_argument("--port-ui", type=int, default=5173, help="Port for Vite dev server (default: 5173)")
    parser.add_argument("--no-frontend", action="store_true", help="Skip running Vite dev server (API serves frontend/dist directly)")
    parser.add_argument("--no-mcp", action="store_true", help="Skip running FastMCP server")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, shutdown_all)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_all)

    print("\n" + "=" * 68)
    print("  MARITIME OPERATIONS ASSISTANT — STARTING ALL SERVICES")
    print("=" * 68)

    check_neo4j()

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["PYTHONUNBUFFERED"] = "1"
    env["MARITIME_MCP_SERVER_URL"] = f"http://localhost:{args.port_mcp}/mcp"
    env["PORT"] = str(args.port_api)

    # 1. Start FastMCP Knowledge Graph Server
    if not args.no_mcp:
        print(f"  [1/3] Starting FastMCP Server on port {args.port_mcp}...")
        mcp_cmd = [
            PYTHON_EXE,
            "-m",
            "knowledge_graph.maritime_kg_mcp.main",
            "--transport",
            "http",
            "--port",
            str(args.port_mcp),
        ]
        p_mcp = subprocess.Popen(mcp_cmd, cwd=str(ROOT_DIR), env=env)
        processes.append(p_mcp)
        time.sleep(1.0)

    # 2. Start AI Agent FastAPI Server
    print(f"  [2/3] Starting AI Agent API Server on port {args.port_api}...")
    api_cmd = [
        PYTHON_EXE,
        "-m",
        "uvicorn",
        "ai_agent.src.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(args.port_api),
        "--reload",
    ]
    p_api = subprocess.Popen(api_cmd, cwd=str(ROOT_DIR), env=env)
    processes.append(p_api)
    time.sleep(1.0)

    # 3. Start Frontend Development Server
    frontend_dir = ROOT_DIR / "frontend"
    npm_bin = "npm.cmd" if os.name == "nt" else "npm"

    if not args.no_frontend and frontend_dir.exists():
        print(f"  [3/3] Starting Frontend Dev Server on port {args.port_ui}...")
        ui_cmd = [npm_bin, "run", "dev", "--", "--port", str(args.port_ui)]
        try:
            p_ui = subprocess.Popen(ui_cmd, cwd=str(frontend_dir), env=env)
            processes.append(p_ui)
        except Exception as exc:
            print(f"  [WARNING] Could not launch npm dev server: {exc}")
            print(f"            Access the bundled UI directly at http://localhost:{args.port_api}")

    print("\n" + "=" * 68)
    print("  ALL SERVICES ARE RUNNING SUCCESSFULLY!")
    print("=" * 68)
    print(f"  * Frontend Web Interface:   http://localhost:{args.port_ui}")
    print(f"  * Integrated Web UI:        http://localhost:{args.port_api}")
    print(f"  * AI Agent Swagger Docs:    http://localhost:{args.port_api}/docs")
    print(f"  * FastMCP Server:           http://localhost:{args.port_mcp}/mcp")
    print("=" * 68)
    print("  Press Ctrl+C to stop all services.\n")

    try:
        while True:
            # Check if any critical child process died unexpectedly
            for p in list(processes):
                ret = p.poll()
                if ret is not None:
                    print(f"\n[ALERT] Service (PID {p.pid}) exited with code {ret}. Shutting down remaining services...")
                    shutdown_all()
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown_all()


if __name__ == "__main__":
    main()

