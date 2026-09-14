import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import engine
from . import models
from .routers import (
    collections,
    dashboard,
    environment,
    exhibitions,
    loans,
    locations,
    restorations,
)

# 自动建表(SQLite / PostgreSQL 均可;如需迁移可在此基础上引入 Alembic)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="博物馆藏品管理系统 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    dashboard.router,
    collections.router,
    locations.router,
    exhibitions.router,
    restorations.router,
    loans.router,
    environment.router,
):
    app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ok", "db": engine.dialect.name}


# 生产模式:若已构建前端(dist 目录存在),由 FastAPI 一并托管
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend_dist"
if DIST_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=DIST_DIR / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        index = DIST_DIR / "index.html"
        if full_path:
            candidate = DIST_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index)
