"""ASGI entrypoint: `uvicorn app.main:app`."""

from app.core.app_factory import create_app

app = create_app()
