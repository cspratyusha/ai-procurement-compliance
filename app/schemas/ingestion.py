from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AmendmentSchema(BaseModel):
    amendment_number: int
    date_issued: Optional[str] = None
    change_summary: str

class CrossReferenceSchema(BaseModel):
    target_standard_number: str
    relationship_type: str = Field(
        ..., 
        description="NORMATIVE_REFERENCE, TEST_METHOD_FOR, SAFETY_REQUIREMENT_FOR, SUPERSEDED_BY, OVERLAPS_SCOPE_WITH"
    )
    description: Optional[str] = None

class StandardIngestSchema(BaseModel):
    standard_number: str = Field(..., example="IS 456:2000")
    title: str
    scope_text: str
    abstract: Optional[str] = None
    year_published: Optional[int] = None
    current_version: Optional[str] = None
    status: str = Field("active", example="active") # active, superseded, withdrawn
    category_id: Optional[str] = None
    sector: Optional[str] = None
    amendments: List[AmendmentSchema] = []
    cross_references: List[CrossReferenceSchema] = []

class ProductCategoryIngestSchema(BaseModel):
    category_id: str = Field(..., example="CAT-STEEL-01")
    name: str
    description: Optional[str] = None
    parent_category_id: Optional[str] = None

class CertificationRuleIngestSchema(BaseModel):
    rule_id: str
    category_id: str
    standard_number: Optional[str] = None
    scheme_type: str = Field(..., example="BIS Product Certification (ISI Mark)")
    mandatory_flag: bool = True
    description: Optional[str] = None

class BatchIngestRequest(BaseModel):
    categories: List[ProductCategoryIngestSchema] = []
    standards: List[StandardIngestSchema] = []
    certification_rules: List[CertificationRuleIngestSchema] = []

class IngestionResponse(BaseModel):
    status: str
    message: str
    postgres_inserted: Dict[str, int]
    neo4j_synced: bool
    vector_db_indexed_count: int
    bm25_indexed_count: int

class IngestionStatsResponse(BaseModel):
    postgres: Dict[str, int]
    neo4j: Dict[str, Any]
    vector_db: Dict[str, Any]
    bm25: Dict[str, Any]
