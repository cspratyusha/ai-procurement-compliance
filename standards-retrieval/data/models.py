from typing import Literal
from pydantic import BaseModel, Field


class Standard(BaseModel):
    """Pydantic model representing an Indian Standard (BIS) document specification."""
    id: str = Field(..., description="Unique internal identifier, e.g., IS-ELEC-001")
    number: str = Field(..., description="Realistic IS-style numbering, e.g. 'IS 1554 (Part 1):2019'")
    title: str = Field(..., description="Full official title of the standard")
    scope: str = Field(..., description="1-3 sentences in formal regulatory tone: 'This standard covers...'")
    description: str = Field(..., description="2-4 sentences, use-case oriented technical summary")
    category: str = Field(..., description="Product/domain classification category")
    version: str = Field(..., description="Version or revision string, e.g. 'Third Revision'")
    last_amended: str = Field(..., description="Date of the latest amendment, YYYY-MM-DD")
    status: Literal["active", "superseded"] = Field(..., description="Current validity status")
    keywords: list[str] = Field(default_factory=list, description="List of domain keywords and technical terms")
