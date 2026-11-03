"""
Authentication Routes for Maritime Operations AI Agent API.
"""

from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field

from ai_agent.src.repo.database import create_user, authenticate_user
from ai_agent.src.api.dependencies import create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


class UserProfile(BaseModel):
    user_id: str = Field(description="Unique operator user identifier.")
    username: str = Field(description="Operator login handle.")
    email: str = Field(description="Operator corporate email address.")
    full_name: str = Field(description="Operator's full name.")
    role: str = Field(description="Operator role (e.g., fleet_dispatcher, port_captain, cargo_superintendent).")
    created_at: Optional[str] = Field(default=None, description="Account creation timestamp.")


class RegisterRequest(BaseModel):
    username: str = Field(description="Unique username for the operator.", min_length=3)
    email: str = Field(description="Corporate email address.")
    password: str = Field(description="Plain text password to be hashed using PBKDF2-SHA256.", min_length=6)
    full_name: str = Field(description="Operator full legal or display name.")
    role: Optional[str] = Field(default="fleet_dispatcher", description="Operational role assignment.")


class LoginRequest(BaseModel):
    username_or_email: str = Field(description="Registered username or email address.")
    password: str = Field(description="Account password.")


class AuthResponse(BaseModel):
    access_token: str = Field(description="Signed JWT access bearer token.")
    token_type: str = Field(default="bearer", description="Token authentication scheme.")
    user: Dict[str, Any] = Field(description="Authenticated user profile attributes.")


class MeResponse(BaseModel):
    user: Dict[str, Any] = Field(description="Authenticated operator details.")


@router.post("/register", response_model=AuthResponse, summary="Register operator", description="Creates a new operator account and returns an authenticated JWT bearer token.")
def register(req: RegisterRequest):
    """Registers a new maritime operator."""
    user = create_user(
        username=req.username,
        email=req.email,
        password=req.password,
        full_name=req.full_name,
        role=req.role or "fleet_dispatcher"
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists."
        )
    token = create_access_token({"sub": user["user_id"], "username": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.post("/login", response_model=AuthResponse, summary="Operator login", description="Authenticates credentials and returns a 24-hour signed JWT access token.")
def login(req: LoginRequest):
    """Authenticates operator credentials and returns access token."""
    user = authenticate_user(req.username_or_email, req.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = create_access_token({"sub": user["user_id"], "username": user["username"], "role": user["role"]})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=MeResponse, summary="Get current operator", description="Retrieves profile and role information for the currently authenticated operator.")
def me(current_user: dict = Depends(get_current_user)):
    """Returns profile of currently logged-in operator."""
    return {"user": current_user}

