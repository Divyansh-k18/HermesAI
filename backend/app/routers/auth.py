"""Authentication routes: register, login, logout, and current-user lookup.

Sessions are opaque random tokens in an HttpOnly cookie. Only their SHA-256 hash is stored.
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.deps import SESSION_COOKIE, CurrentAuth, get_current_auth, get_db, require_csrf, trace_id_of
from app.models import AuthSession, User, utcnow
from app.schemas import AuthOut, LoginIn, RegisterIn, UserOut
from app.security import (
    burn_password_check,
    hash_password,
    hash_token,
    new_csrf_token,
    new_token,
    password_policy_errors,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _start_session(request: Request, db: Session, user: User, response: Response) -> str:
    settings = request.app.state.settings
    token = new_token()
    csrf = new_csrf_token()
    db.add(
        AuthSession(
            token_hash=hash_token(token),
            csrf_token=csrf,
            user_id=user.id,
            expires_at=utcnow() + timedelta(hours=settings.session_ttl_hours),
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    return csrf


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=AuthOut)
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthOut:
    if not request.app.state.login_limiter.allow(f"register:{_client_key(request)}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many attempts. Try again later.")
    errors = password_policy_errors(payload.password)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=errors)
    if db.scalar(select(User.id).where(User.email == payload.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    user = User(email=payload.email, full_name=payload.full_name.strip(), password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    csrf = _start_session(request, db, user, response)
    record_audit(
        db,
        action="auth.register",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return AuthOut(user=UserOut(id=user.id, email=user.email, full_name=user.full_name), csrf_token=csrf)


@router.post("/login", response_model=AuthOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthOut:
    limiter = request.app.state.login_limiter
    if not limiter.allow(f"login:{_client_key(request)}:{payload.email}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many login attempts. Try again later.")

    user = db.scalar(select(User).where(User.email == payload.email))
    if user is None:
        burn_password_check(payload.password)
        record_audit(
            db,
            action="auth.login",
            outcome="failure",
            metadata={"reason": "unknown_account"},
            trace_id=trace_id_of(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    if not verify_password(user.password_hash, payload.password) or not user.is_active:
        record_audit(
            db,
            action="auth.login",
            outcome="failure",
            actor_user_id=user.id,
            metadata={"reason": "bad_credentials_or_inactive"},
            trace_id=trace_id_of(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    csrf = _start_session(request, db, user, response)
    record_audit(
        db,
        action="auth.login",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    return AuthOut(user=UserOut(id=user.id, email=user.email, full_name=user.full_name), csrf_token=csrf)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    auth: CurrentAuth = Depends(require_csrf),
    db: Session = Depends(get_db),
) -> Response:
    session_row = db.get(AuthSession, auth.session.id)
    if session_row is not None:
        session_row.revoked_at = utcnow()
    record_audit(
        db,
        action="auth.logout",
        actor_user_id=auth.user.id,
        target_type="user",
        target_id=auth.user.id,
        trace_id=trace_id_of(request),
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=AuthOut)
def me(auth: CurrentAuth = Depends(get_current_auth)) -> AuthOut:
    return AuthOut(
        user=UserOut(id=auth.user.id, email=auth.user.email, full_name=auth.user.full_name),
        csrf_token=auth.session.csrf_token,
    )
