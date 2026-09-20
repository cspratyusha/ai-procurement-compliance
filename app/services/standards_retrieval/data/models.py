from typing import Literal, Optional, List
from pydantic import BaseModel, Field


class Standard(BaseModel):
    """Pydantic model representing an Indian Standard (BIS) document specification."""
    id: str = Field(..., description="Unique internal identifier, e.g., std_001 or IS-ELEC-001")
    number: str = Field(..., description="Official BIS designation, e.g. 'IS 2062:2011'")
    title: str = Field(..., description="Full official title of the standard")
    scope: str = Field(..., description="Scope of the standard")
    description: str = Field(..., description="Technical summary / procurement description")
    category: str = Field(..., description="Product/domain classification category")
    version: str = Field(..., description="Version or revision string, e.g. '2011'")
    last_amended: str = Field(..., description="Date of the latest amendment, YYYY-MM-DD")
    status: Literal["active", "superseded", "withdrawn"] = Field(..., description="Current validity status")
    keywords: List[str] = Field(default_factory=list, description="List of domain keywords and technical terms")
    superseded_by_id: Optional[str] = Field(default=None, description="Direct standard ID that supersedes this standard")
