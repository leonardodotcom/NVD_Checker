from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import auth

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginIn, request: Request):
    if auth.is_locked(body.username):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    username = auth.authenticate(body.username, body.password)
    if not username:
        auth.record_failure(body.username)
        raise HTTPException(401, "Invalid username or password")
    auth.clear_failures(body.username)
    request.session.clear()
    request.session["user"] = username
    return {"user": username}


@router.post("/logout", status_code=204)
def logout(request: Request):
    request.session.clear()


@router.get("/me")
def me(user: str = Depends(auth.require_user)):
    return {"user": user}
