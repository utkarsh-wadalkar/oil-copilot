from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.main import create_app
from app.models import Conversation, ImportBatch
from app.schemas import AnswerEnvelope


def test_answer_envelope_validates_and_rejects_unknown_fields():
    data = {"result_id": "r1", "question": "Q", "analysis_date": "2026-10-17",
            "summary": "A", "visual": {"kind": "card", "title": "Answer"}, "extra": True}
    try:
        AnswerEnvelope.model_validate(data)
    except ValueError:
        pass
    else:
        raise AssertionError("unknown fields must be rejected")
    data.pop("extra")
    assert AnswerEnvelope.model_validate(data).analysis_date.isoformat() == "2026-10-17"


def test_sqlite_roundtrip_and_health(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(engine, expire_on_commit=False)
    with TestingSession() as session:
        batch = ImportBatch(revision="r1", root="/data", manifest_hash="h")
        session.add(batch)
        session.add(Conversation(user_id="u1", title="Test"))
        session.commit()
        assert session.scalar(select(ImportBatch)).id == batch.id
    app = create_app(engine)

    class WrongSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, *_args, **_kwargs):
            raise AssertionError("app used the global session factory instead of its injected engine")

    monkeypatch.setattr("app.db.SessionLocal", lambda: WrongSession())
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
