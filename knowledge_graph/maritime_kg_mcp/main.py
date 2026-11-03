"""Entrypoint to launch the Maritime Knowledge Graph MCP & Swagger API Server."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Enable direct script execution as well as module execution (-m)
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import uvicorn
from knowledge_graph.maritime_kg_mcp.api import mcp_app
from knowledge_graph.maritime_kg_mcp.server import mcp


def main():
    parser = argparse.ArgumentParser(
        description="Maritime Knowledge Graph FastMCP Server with Swagger Documentation"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http", "streamable-http"],
        default="http",
        help="MCP transport protocol (default: http, which provides both Swagger UI at /docs and MCP at /mcp)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP/SSE transport (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for HTTP/SSE transport (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    if args.transport in ["http", "streamable-http"]:
        print(
            f"Starting Maritime Knowledge Graph MCP & REST Server...\n"
            f" - Swagger Documentation: http://{args.host}:{args.port}/docs\n"
            f" - ReDoc Documentation:   http://{args.host}:{args.port}/redoc\n"
            f" - OpenAPI Specification: http://{args.host}:{args.port}/openapi.json\n"
            f" - FastMCP Protocol:      http://{args.host}:{args.port}/mcp\n"
            f" - Tools Catalog:         http://{args.host}:{args.port}/tools\n",
            file=sys.stderr,
        )
        uvicorn.run(mcp_app, host=args.host, port=args.port)
    elif args.transport == "sse":
        print(f"Starting FastMCP SSE Server on {args.host}:{args.port}...", file=sys.stderr)
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
