from fastapi import Request

from app.services.rag.engine import RagEngine


def get_engine(request: Request) -> RagEngine:
    return request.app.state.engine
