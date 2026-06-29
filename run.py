"""Entry point for the MTG Deck Builder app.

Run with: python run.py
Then open: http://127.0.0.1:8000
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.application:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
