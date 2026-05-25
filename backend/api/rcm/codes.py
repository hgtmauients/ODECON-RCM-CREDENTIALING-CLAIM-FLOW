"""
ClaimFlow - Code Library API.
Search ICD-10 and CPT codes with autocomplete support.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import Optional

from core.database import get_db
from api.auth import get_current_user, Principal
from models.code_library import ICD10Code, CPTCode

router = APIRouter(prefix="/rcm/codes", tags=["RCM - Code Library"])


@router.get("/icd10")
async def search_icd10(
    q: str = Query(..., min_length=1, description="Search by code or description"),
    category: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Search ICD-10 diagnosis codes. Used for autocomplete on claim forms."""
    current_user.require_role("billing")
    query = select(ICD10Code)
    search = f"%{q}%"
    query = query.where(or_(
        ICD10Code.code.ilike(search),
        ICD10Code.short_description.ilike(search),
    ))
    if category:
        query = query.where(ICD10Code.category == category)
    query = query.where(ICD10Code.is_billable == True)
    query = query.order_by(ICD10Code.code).limit(limit)

    result = await db.execute(query)
    codes = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "code": c.code,
            "description": c.short_description,
            "category": c.category,
        } for c in codes],
    }


@router.get("/cpt")
async def search_cpt(
    q: str = Query(..., min_length=1, description="Search by code or description"),
    category: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """Search CPT/HCPCS procedure codes. Used for autocomplete on claim forms."""
    current_user.require_role("billing")
    query = select(CPTCode)
    search = f"%{q}%"
    query = query.where(or_(
        CPTCode.code.ilike(search),
        CPTCode.short_description.ilike(search),
    ))
    if category:
        query = query.where(CPTCode.category == category)
    query = query.where(CPTCode.is_active == True)
    query = query.order_by(CPTCode.code).limit(limit)

    result = await db.execute(query)
    codes = result.scalars().all()

    return {
        "success": True,
        "data": [{
            "code": c.code,
            "description": c.short_description,
            "category": c.category,
            "subcategory": c.subcategory,
        } for c in codes],
    }


@router.get("/icd10/categories")
async def list_icd10_categories(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List ICD-10 categories for filtering."""
    current_user.require_role("billing")
    from sqlalchemy import func, distinct
    result = await db.execute(select(distinct(ICD10Code.category)).where(ICD10Code.category.isnot(None)).order_by(ICD10Code.category))
    cats = [r[0] for r in result.fetchall()]
    return {"success": True, "data": cats}


@router.get("/cpt/categories")
async def list_cpt_categories(
    db: AsyncSession = Depends(get_db),
    current_user: Principal = Depends(get_current_user),
):
    """List CPT categories for filtering."""
    current_user.require_role("billing")
    from sqlalchemy import func, distinct
    result = await db.execute(select(distinct(CPTCode.category)).where(CPTCode.category.isnot(None)).order_by(CPTCode.category))
    cats = [r[0] for r in result.fetchall()]
    return {"success": True, "data": cats}
