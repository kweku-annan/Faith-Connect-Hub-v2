
FastAPI + PostgreSQL backend for managing church attendance, members, groups, and fellowship data.

## Stack
- **Python 3.11+**
- **FastAPI** — web framework
- **SQLAlchemy 2.0** (async) — ORM
- **PostgreSQL** — database
- **Alembic** — migrations
- **Passlib/bcrypt** — password hashing
- **python-jose** — JWT tokens

## Project Structure
```
palace_cell_app/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Settings from .env
│   ├── api/v1/
│   │   ├── router.py        # Aggregates all endpoint routers
│   │   ├── dependencies.py  # Auth dependencies (get_current_user, require_roles)
│   │   └── endpoints/       # One file per resource
│   ├── core/
│   │   ├── security.py      # JWT + password hashing
│   │   ├── permissions.py   # Role-permission mapping
│   │   └── exceptions.py    # HTTP exception classes
│   ├── db/
│   │   ├── base.py          # DeclarativeBase + model imports for Alembic
│   │   └── session.py       # Async engine + get_db dependency
│   ├── models/              # SQLAlchemy ORM models
│   ├── schemas/             # Pydantic request/response schemas
│   ├── services/            # Business logic layer
│   └── utils/
│       ├── validators.py    # Phone number validation (+233XXXXXXXXX)
│       └── pagination.py    # Reusable pagination helpers
├── alembic/                 # Database migrations
├── tests/                   # Unit and integration tests
├── .env.example
└── requirements.txt
```

## Getting Started

```bash
# 1. Clone and create virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your DATABASE_URL and SECRET_KEY

# 4. Run migrations
alembic upgrade head

# 5. Start the server
uvicorn app.main:app --reload
```

API docs available at: http://localhost:8000/docs

## Roles
| Role | Capabilities |
|---|---|
| `super_admin` | Everything |
| `admin` | Create groups, assign members, transfer members/leaders |
| `pastor` | Assign group members, view all groups, mark attendance |
| `leader` | Manage their group's members, mark attendance for their group |