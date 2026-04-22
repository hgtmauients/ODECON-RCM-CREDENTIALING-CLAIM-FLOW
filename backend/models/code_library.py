"""
ClaimFlow - ICD-10 and CPT/HCPCS code reference models.
Searchable code libraries for claim creation and validation.
"""

from sqlalchemy import Column, Integer, String, Text, Boolean, Index
from models.base import Base


class ICD10Code(Base):
    """ICD-10-CM diagnosis codes. ~72,000 codes published by CMS annually."""
    __tablename__ = "icd10_codes"
    __table_args__ = (
        Index("ix_icd10_code", "code", unique=True),
        Index("ix_icd10_search", "code", "short_description"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), nullable=False, unique=True)
    short_description = Column(String(255), nullable=False)
    long_description = Column(Text)
    category = Column(String(100))
    chapter = Column(String(255))
    is_billable = Column(Boolean, default=True)

    def __repr__(self):
        return f"<ICD10Code({self.code}: {self.short_description})>"


class CPTCode(Base):
    """CPT/HCPCS procedure codes for physician billing."""
    __tablename__ = "cpt_codes"
    __table_args__ = (
        Index("ix_cpt_code", "code", unique=True),
        Index("ix_cpt_search", "code", "short_description"),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), nullable=False, unique=True)
    short_description = Column(String(255), nullable=False)
    long_description = Column(Text)
    category = Column(String(100))
    subcategory = Column(String(100))
    rvu_work = Column(String(10))
    rvu_facility = Column(String(10))
    rvu_nonfacility = Column(String(10))
    is_active = Column(Boolean, default=True)

    def __repr__(self):
        return f"<CPTCode({self.code}: {self.short_description})>"
