"""Read-only Registry-backed Personal Account destination catalog."""

from fastapi import APIRouter, HTTPException

from schemas import AccountCatalogResponse
from services.account_catalog import AccountCatalogError, load_account_catalog

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/catalog", response_model=AccountCatalogResponse)
async def get_account_catalog() -> AccountCatalogResponse:
    """Return approved routing metadata; never document contents or write authority."""
    try:
        return load_account_catalog()
    except AccountCatalogError as error:
        raise HTTPException(status_code=503, detail="Account catalog is unavailable") from error
