"""Main FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import alert_routes, maintenance_routes, sensor_routes, worker_routes
from app.core.db import create_tables
from app.core.exceptions import ApplicationError, SensorValidationError
from app.graph.builder import build_safety_graph
from app.models.orm_models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create DB tables and compile the safety graph once on startup.

    No scheduler: there's no real IoT sensor yet, so every reading (both
    the initial periodic-style one and later recheck ones) arrives as a
    manually-submitted request through `sensor_routes` instead of being
    polled on a timer.

    The graph is compiled once here (not per-request) and kept on
    `app.state` - its checkpointer holds per-thread state in memory, so
    rebuilding it on every request would silently drop that state between
    calls instead of letting a recheck resume the same thread.
    """

    await create_tables(Base)
    app.state.safety_graph = build_safety_graph()
    yield


app = FastAPI(
    title="Industrial Safety Multi-Agent System API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(sensor_routes.router)
app.include_router(alert_routes.router)
app.include_router(worker_routes.router)
app.include_router(maintenance_routes.router)


@app.exception_handler(ApplicationError)
async def handle_application_error(request: Request, exc: ApplicationError) -> JSONResponse:
    """Map the shared error-code exception hierarchy onto an HTTP response.

    Without this, any raised `ApplicationError` (SensorValidationError,
    DatabaseOperationError, WorkerResponseSaveError, ...) propagates as an
    unhandled exception and crashes the request with a raw traceback instead
    of a JSON error body.
    """

    status_code = 422 if isinstance(exc, SensorValidationError) else 500
    return JSONResponse(
        status_code=status_code,
        content={"error_code": exc.error_code, "message": str(exc), "details": exc.details},
    )
