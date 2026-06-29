"""Vercel serverless entry point.

Vercel's Python runtime auto-detects an ASGI app object named ``app`` in any
file under ``api/``. Importing it here is enough — no handler code needed.
The FastAPI lifespan (which runs ``init_db``) fires on cold start of the
function instance.
"""
import os
import sys

# Vercel's serverless runtime does not always put the project root on
# sys.path (it tends to add only the entrypoint file's directory). Without
# this, ``from app.application import app`` raises ModuleNotFoundError
# because the ``app`` package (sibling of ``api/``) is not importable.
# Insert the project root explicitly so the package resolves.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.application import app  # noqa: E402,F401  (Vercel auto-detects the `app` ASGI object)

