import datetime as dt
import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reserveme import db  # noqa: E402
from reserveme.models import Base, Guest, RatePlan, Room, RoomType, User  # noqa: E402
from reserveme.seed import seed_required, seed_sample  # noqa: E402
from reserveme.services.common import Actor  # noqa: E402

BDATE = dt.date(2026, 11, 2)  # a Monday

URLS = {"sqlite": "sqlite:///:memory:"}
if os.environ.get("RM_TEST_PG_URL"):
    URLS["postgresql"] = os.environ["RM_TEST_PG_URL"]
if os.environ.get("RM_TEST_MYSQL_URL"):
    URLS["mysql"] = os.environ["RM_TEST_MYSQL_URL"]


@pytest.fixture(params=list(URLS))
def database(request):
    url = URLS[request.param]
    if url.startswith("sqlite"):
        from sqlalchemy.pool import StaticPool
        from sqlalchemy import create_engine
        eng = create_engine(url, poolclass=StaticPool, connect_args={"check_same_thread": False})
        db._engine = eng
        from sqlalchemy.orm import sessionmaker
        db._Session = sessionmaker(bind=eng, expire_on_commit=False)
    else:
        eng = db.init(url)
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    with db.session() as s:
        seed_required(s, business_date=BDATE)
        seed_sample(s)
    yield request.param
    db.engine().dispose()
    if not url.startswith("sqlite"):
        Base.metadata.drop_all(db.make_engine(url))


@pytest.fixture
def admin(database):
    with db.session() as s:
        u = s.scalar(select(User).where(User.username == "admin"))
        return Actor(u.id, u.username, u.full_name, u.role)


@pytest.fixture
def refs(database):
    with db.session() as s:
        types = {t.code: t.id for t in s.scalars(select(RoomType))}
        rooms = {r.number: r.id for r in s.scalars(select(Room))}
        plans = {p.code: p.id for p in s.scalars(select(RatePlan))}
        guests = [g.id for g in s.scalars(select(Guest).order_by(Guest.id))]
    return dict(types=types, rooms=rooms, plans=plans, guests=guests)
