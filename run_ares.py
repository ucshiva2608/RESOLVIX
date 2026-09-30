#!/usr/bin/env python3
"""
ARES — Autonomous Response Engineering System
Detect. Investigate. Decide. Act. Verify.

One-command launcher for backend API, real-time SSE stream, and SRE Mission Control dashboard.
"""

import os
import sys
import uvicorn

BANNER = """
========================================================================
     █████╗ ██████╗ ███████╗███████╗
    ██╔══██╗██╔══██╗██╔════╝██╔════╝
    ███████║██████╔╝█████╗  ███████╗
    ██╔══██║██╔══██╗██╔══╝  ╚════██║
    ██║  ██║██║  ██║███████╗███████║
    ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝
    AUTONOMOUS RESPONSE ENGINEERING SYSTEM
    Detect. Investigate. Decide. Act. Verify.
========================================================================
   • SRE Mission Control: http://127.0.0.1:8000
   • API Docs (Swagger): http://127.0.0.1:8000/docs
   • Initial Computation Budget: 10,000 Tokens
   • Safety Policy Gate: ENFORCED (Zero arbitrary shell access)
========================================================================
"""

def main():
    print(BANNER)
    # Ensure current directory is in Python path
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

    # Run Uvicorn server
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
