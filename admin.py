"""Точка входа для админ-панели."""
import uvicorn
from src.admin.app import app

if __name__ == "__main__":
    uvicorn.run(
        "src.admin.app:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )

