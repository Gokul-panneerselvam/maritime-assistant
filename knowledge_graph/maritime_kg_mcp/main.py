"""Entrypoint to launch the Maritime Knowledge Graph MCP Server."""
import argparse
import sys
from pathlib import Path

# Enable direct script execution as well as module execution (-m)
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_graph.maritime_kg_mcp.server import mcp

def main():
    parser = argparse.ArgumentParser(
        description="Maritime Knowledge Graph FastMCP Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-stdio"],
        default="stdio",
        help="MCP transport protocol (default: stdio)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for SSE transport (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for SSE transport (default: 127.0.0.1)"
    )

    args = parser.parse_args()

    print(f"Starting Maritime Knowledge Graph MCP Server (transport: {args.transport})...", file=sys.stderr)
    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()

