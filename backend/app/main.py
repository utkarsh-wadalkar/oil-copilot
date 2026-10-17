from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import engine, get_session, init_db, session_dependency
from app.routes import create_router


def create_app(database_engine=engine, settings: Settings | None = None, provider=None, memory=None,
               graph=None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def app_lifespan(_: FastAPI):
        init_db(database_engine)
        yield

    application = FastAPI(title="Asset Intelligence Copilot API", lifespan=app_lifespan)
    application.dependency_overrides[get_session] = session_dependency(database_engine)
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                               allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

    @application.get("/health")
    def health(session: Session = Depends(get_session)):
        try:
            session.execute(text("SELECT 1"))
        except Exception:
            return {"status": "degraded", "database": "unavailable"}
        return {"status": "ok", "database": "ok"}

    application.include_router(create_router(settings, provider=provider, memory=memory, graph=graph))
    return application


app = create_app()
