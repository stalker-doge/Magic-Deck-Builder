"""Vercel serverless entry point.

Vercel's Python runtime auto-detects an ASGI app object named ``app`` in any
file under ``api/``. Importing it here is enough — no handler code needed.
The FastAPI lifespan (which runs ``init_db``) fires on cold start of the
function instance.
"""
from app.main import app  # noqa: F401  (Vercel auto-detects the `app` ASGI object)
