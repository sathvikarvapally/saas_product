from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import router
from app.core.config import get_settings
from app.core.errors import ConflictError, InvalidRequestError, NotFoundError

app = FastAPI(title=get_settings().app_name, version="0.1.0")
app.include_router(router)


@app.exception_handler(NotFoundError)
async def handle_not_found(request: Request, error: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(ConflictError)
async def handle_conflict(request: Request, error: ConflictError):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(InvalidRequestError)
async def handle_invalid_request(request: Request, error: InvalidRequestError):
    return JSONResponse(status_code=422, content={"detail": str(error)})
