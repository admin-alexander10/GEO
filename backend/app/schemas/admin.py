from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class OwnerLoginRequest(BaseModel):
    access_key: str = Field(..., min_length=1, max_length=256)


class OwnerLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    must_change_password: bool = False


class OwnerPasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=128)


class InstitutionApplicationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_name: str
    ruc: str
    institution_type: str
    region: str
    official_email: str
    contact_name: str
    contact_phone: str
    evidence_url: str
    applicant_username: str
    status: str
    submitted_at: datetime
    verification_source: Optional[str] = None
    review_notes: Optional[str] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class InstitutionApprovalRequest(BaseModel):
    verification_source: str = Field(..., min_length=12, max_length=500)
    review_notes: str = Field(..., min_length=10, max_length=2000)


class InstitutionRejectionRequest(BaseModel):
    review_notes: str = Field(..., min_length=10, max_length=2000)


class InstitutionReviewResponse(BaseModel):
    id: int
    institution_name: str
    status: str
    reviewed_by: str
    reviewed_at: Optional[datetime] = None
    message: str


class InstitutionCoverageItem(BaseModel):
    """Institución activa y su cobertura geográfica (centro + radio)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    institution_name: str
    is_active: bool
    coverage_lat: Optional[float] = None
    coverage_lng: Optional[float] = None
    coverage_radius_km: Optional[float] = None
    coverage_evidence: Optional[str] = None
    coverage_validated_by: Optional[str] = None
    coverage_validated_at: Optional[datetime] = None


class InstitutionCoverageRequest(BaseModel):
    latitud: float = Field(..., ge=-90, le=90)
    longitud: float = Field(..., ge=-180, le=180)
    radio_km: float = Field(..., gt=0, le=500)
    # Qué documento o fuente respalda que la institución atiende esa zona.
    evidencia: str = Field(..., min_length=10, max_length=2000)
