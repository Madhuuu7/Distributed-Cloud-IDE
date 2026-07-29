from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/signup", response_model=TokenResponse)
def signup(payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        existing = db.query(User).filter(User.email == str(payload.email)).first()

        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user = User(
            email=str(payload.email),
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token(str(user.id))
        return TokenResponse(access_token=token)

    except Exception as e:
        print("SIGNUP ERROR:", repr(e))
        raise


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == str(payload.email)).first()

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)