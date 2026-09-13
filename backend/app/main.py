import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from app.core.config import settings
from app.db.mongodb import connect_to_mongo, close_mongo_connection, db_manager, get_database
from app.api.v1.api import api_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("resilience")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing RESILIENCE Emergency Response Backend (Phase 0)...")
    await connect_to_mongo()
    yield
    logger.info("Shutting down RESILIENCE Emergency Response Backend...")
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version="0.1.0-phase9",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    expose_headers=[
        "Content-Type",
        "Authorization",
        "Content-Length",
        "X-Request-Id",
    ],
    max_age=86400,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        loc = " -> ".join(str(l) for l in error.get("loc", []))
        msg = error.get("msg", "Invalid parameter")
        errors.append(f"{loc}: {msg}")
    summary_msg = "; ".join(errors) if errors else "Validation error"
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "detail": summary_msg,
            "message": summary_msg,
            "errors": errors,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled operational exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal operational error occurred. The incident has been recorded in audit logs."},
    )


from fastapi.staticfiles import StaticFiles

# Mount uploads static directory
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Mount API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)



@app.get("/api/docs", include_in_schema=False)
async def api_docs_redirect():
    return RedirectResponse(url="/docs")


@app.get("/api/redoc", include_in_schema=False)
async def api_redoc_redirect():
    return RedirectResponse(url="/redoc")


@app.get("/api/openapi.json", include_in_schema=False)
async def api_openapi_redirect():
    return RedirectResponse(url="/openapi.json")


@app.get("/")
async def root():
    return {
        "system": "RESILIENCE",
        "description": "AI-Powered Community Emergency Response & Resource Coordination Platform",
        "phase": "Phase 9 (Emergency Intelligence & Integrated Operations)",
        "status": "OPERATIONAL",
        "api_docs": "/docs",
        "openapi_url": "/openapi.json",
        "version": "0.1.0-phase9",
    }


@app.get("/health", tags=["System Telemetry & Health"])
@app.head("/health", include_in_schema=False)
async def root_health():
    db_connected = False
    try:
        if db_manager.client is not None:
            await db_manager.client.admin.command("ping")
            db_connected = True
        elif db_manager.db is not None:
            await db_manager.db.command("ping")
            db_connected = True
        else:
            db = get_database()
            await db.command("ping")
            db_connected = True
    except Exception:
        db_connected = False

    return {
        "status": "healthy",
        "system": "RESILIENCE",
        "database": "connected" if db_connected else "disconnected",
        "phases_active": "0-9",
    }
