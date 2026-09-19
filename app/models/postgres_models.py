import datetime
import uuid
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class ProductCategoryModel(Base):
    __tablename__ = "product_categories"

    category_id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    parent_category_id = Column(String(50), ForeignKey("product_categories.category_id"), nullable=True)

    standards = relationship("StandardModel", back_populates="category")
    certification_rules = relationship("CertificationRuleModel", back_populates="category")

class StandardModel(Base):
    __tablename__ = "standards"

    standard_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    standard_number = Column(String(100), unique=True, nullable=False, index=True) # e.g. IS 456:2000
    title = Column(String(500), nullable=False)
    scope_text = Column(Text, nullable=False)
    abstract = Column(Text, nullable=True)
    year_published = Column(Integer, nullable=True)
    current_version = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, default="active") # active, superseded, withdrawn
    category_id = Column(String(50), ForeignKey("product_categories.category_id"), nullable=True)
    sector = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    category = relationship("ProductCategoryModel", back_populates="standards")
    amendments = relationship("AmendmentModel", back_populates="standard", cascade="all, delete-orphan")

class AmendmentModel(Base):
    __tablename__ = "amendments"

    amendment_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    standard_number = Column(String(100), ForeignKey("standards.standard_number"), nullable=False)
    amendment_number = Column(Integer, nullable=False)
    date_issued = Column(String(50), nullable=True)
    change_summary = Column(Text, nullable=False)

    standard = relationship("StandardModel", back_populates="amendments")

class CrossReferenceModel(Base):
    __tablename__ = "cross_references"

    reference_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_standard_number = Column(String(100), nullable=False, index=True)
    target_standard_number = Column(String(100), nullable=False, index=True)
    relationship_type = Column(String(100), nullable=False) # NORMATIVE_REFERENCE, TEST_METHOD_FOR, etc.
    description = Column(Text, nullable=True)

class CertificationRuleModel(Base):
    __tablename__ = "certification_rules"

    rule_id = Column(String(50), primary_key=True)
    category_id = Column(String(50), ForeignKey("product_categories.category_id"), nullable=False)
    standard_number = Column(String(100), nullable=True)
    scheme_type = Column(String(100), nullable=False) # BIS Product Cert, CRS, Hallmarking
    mandatory_flag = Column(Boolean, default=True)
    description = Column(Text, nullable=True)

    category = relationship("ProductCategoryModel", back_populates="certification_rules")

class InteractionLogModel(Base):
    __tablename__ = "interaction_logs"

    interaction_id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(100), nullable=True)
    org_id = Column(String(100), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    normalised_query = Column(Text, nullable=False)
    input_mode = Column(String(50), default="text")
    candidates_shown = Column(Text, nullable=True) # JSON string
    user_action = Column(String(50), nullable=True) # accepted, rejected, corrected
    corrected_to_standard_number = Column(String(100), nullable=True)
