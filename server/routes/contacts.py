"""Contacts, file parsing, mapping templates, and list management APIs."""
from __future__ import annotations

import base64
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from sqlalchemy import delete, desc, func, select

from server.auth.api_tenant import ApiTenantContext, require_api_tenant
from server.auth.rbac import require_role_permission
from server.db.connection import get_session_factory
from server.db.models.phase5_models import Contact, ContactImportTemplate, ContactList
from server.services.saas.contact_import_service import (
    CANONICAL_FIELDS,
    detect_column_mappings,
    normalize_and_validate_contacts,
    parse_file_to_rows,
)

router = APIRouter()


class ParseJsonBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_name: str = Field("contacts.csv", validation_alias=AliasChoices("fileName", "file_name"))
    content_base64: str | None = Field(None, validation_alias=AliasChoices("contentBase64", "content_base64"))
    raw_text: str | None = Field(None, validation_alias=AliasChoices("rawText", "raw_text", "text"))


class NormalizePreviewBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[dict[str, Any]] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)
    default_country: str = Field("US", validation_alias=AliasChoices("defaultCountry", "default_country"))
    duplicate_strategy: str = Field("keep_first", validation_alias=AliasChoices("duplicateStrategy", "duplicate_strategy"))
    source_file_name: str = Field("uploaded_file", validation_alias=AliasChoices("sourceFileName", "source_file_name"))


class SaveTemplateBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    template_name: str = Field(..., validation_alias=AliasChoices("templateName", "template_name"))
    source_headers: list[str] = Field(..., validation_alias=AliasChoices("sourceHeaders", "source_headers"))
    mapping: dict[str, str] = Field(...)
    default_country: str = Field("US", validation_alias=AliasChoices("defaultCountry", "default_country"))


class CreateListBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    contacts: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/api/contacts/parse")
async def parse_contacts_file(
    request: Request,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    file_bytes: bytes = b""
    file_name: str = "contacts.csv"

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            file_name = getattr(uploaded_file, "filename", "uploaded_file") or "uploaded_file"
            file_bytes = await uploaded_file.read()
    else:
        try:
            body_dict = await request.json()
        except Exception:
            body_dict = {}

        file_name = body_dict.get("fileName") or body_dict.get("file_name") or "contacts.csv"
        raw_b64 = body_dict.get("contentBase64") or body_dict.get("content_base64")
        raw_text = body_dict.get("rawText") or body_dict.get("raw_text") or body_dict.get("text")

        if raw_b64:
            try:
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                file_bytes = base64.b64decode(raw_b64)
            except Exception as e:
                raise HTTPException(status_code=400, detail={"error": {"code": "bad_base64", "message": str(e)}})
        elif raw_text:
            file_bytes = raw_text.encode("utf-8")

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "missing_file", "message": "No file content provided"}},
        )

    # 1. Parse file
    try:
        headers, preview_rows, total_rows, warnings = parse_file_to_rows(file_bytes, file_name, max_preview_rows=50)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "parse_error", "message": str(exc)}})

    if not headers:
        raise HTTPException(status_code=400, detail={"error": {"code": "empty_file", "message": "No columns or data detected"}})

    # 2. Check for saved tenant template matching these headers
    factory = get_session_factory()
    saved_template = None
    if factory:
        async with factory() as session:
            templates = await session.execute(
                select(ContactImportTemplate).where(ContactImportTemplate.tenant_id == ctx.workspace_tenant_id)
            )
            h_set = {h.strip().lower() for h in headers}
            for t in templates.scalars().all():
                src_set = {str(x).strip().lower() for x in (t.source_headers or [])}
                # Check for high overlap (>= 80% matches)
                if h_set and src_set and len(h_set.intersection(src_set)) / len(h_set) >= 0.8:
                    saved_template = {
                        "templateId": str(t.id),
                        "templateName": t.template_name,
                        "mapping": t.mapping,
                        "defaultCountry": t.default_country,
                    }
                    break

    # 3. Detect column mappings with confidence
    template_mapping = saved_template["mapping"] if saved_template else None
    detected = detect_column_mappings(headers, preview_rows, saved_template_mapping=template_mapping)

    return {
        "ok": True,
        "fileName": file_name,
        "totalRows": total_rows,
        "headers": headers,
        "previewRows": preview_rows,
        "detectedMappings": detected,
        "recognizedTemplate": saved_template,
        "warnings": warnings,
        "canonicalFields": [
            {"key": k, "label": v["label"], "category": v["category"], "description": v["description"]}
            for k, v in CANONICAL_FIELDS.items()
        ],
    }


@router.post("/api/contacts/normalize-preview")
async def preview_normalized_contacts(
    body: NormalizePreviewBody,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    if not body.rows:
        return {
            "ok": True,
            "totalRows": 0,
            "validCount": 0,
            "invalidCount": 0,
            "duplicateCount": 0,
            "validContacts": [],
            "invalidContacts": [],
            "duplicateContacts": [],
        }

    res = normalize_and_validate_contacts(
        rows=body.rows,
        mapping=body.mapping,
        default_country=body.default_country,
        duplicate_strategy=body.duplicate_strategy,
        source_file_name=body.source_file_name,
    )
    return {
        "ok": True,
        "totalRows": res["total_rows"],
        "validCount": res["valid_count"],
        "invalidCount": res["invalid_count"],
        "duplicateCount": res["duplicate_count"],
        "validContacts": res["valid_contacts"][:50],  # preview up to 50
        "invalidContacts": res["invalid_contacts"][:50],
        "duplicateContacts": res["duplicate_contacts"][:50],
    }


@router.get("/api/contacts/templates")
async def list_import_templates(ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if not factory:
        return {"templates": []}
    async with factory() as session:
        result = await session.execute(
            select(ContactImportTemplate)
            .where(ContactImportTemplate.tenant_id == ctx.workspace_tenant_id)
            .order_by(desc(ContactImportTemplate.created_at))
        )
        return {
            "templates": [
                {
                    "id": str(r.id),
                    "templateName": r.template_name,
                    "sourceHeaders": r.source_headers,
                    "mapping": r.mapping,
                    "defaultCountry": r.default_country,
                    "createdAt": r.created_at.isoformat() if r.created_at else None,
                }
                for r in result.scalars().all()
            ]
        }


@router.post("/api/contacts/templates")
async def save_import_template(
    body: SaveTemplateBody,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if not factory:
        raise HTTPException(status_code=503, detail="Database not configured")

    tid = uuid.uuid4()
    async with factory() as session:
        # Check existing with same name
        existing = await session.execute(
            select(ContactImportTemplate).where(
                ContactImportTemplate.tenant_id == ctx.workspace_tenant_id,
                func.lower(ContactImportTemplate.template_name) == body.template_name.strip().lower(),
            )
        )
        row = existing.scalar_one_or_none()
        if row:
            row.source_headers = body.source_headers
            row.mapping = body.mapping
            row.default_country = body.default_country
            row.updated_at = datetime.now(timezone.utc)
            tid = row.id
        else:
            session.add(
                ContactImportTemplate(
                    id=tid,
                    tenant_id=ctx.workspace_tenant_id,
                    template_name=body.template_name.strip(),
                    source_headers=body.source_headers,
                    mapping=body.mapping,
                    default_country=body.default_country,
                )
            )
        await session.commit()

    return {"ok": True, "templateId": str(tid), "templateName": body.template_name}


@router.get("/api/contacts/lists")
async def list_contact_lists(ctx: ApiTenantContext = Depends(require_api_tenant)):
    require_role_permission(ctx.role, "app.calls.read")
    factory = get_session_factory()
    if not factory:
        return {"lists": []}
    async with factory() as session:
        result = await session.execute(
            select(ContactList)
            .where(ContactList.tenant_id == ctx.workspace_tenant_id)
            .order_by(desc(ContactList.created_at))
        )
        return {
            "lists": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "description": r.description,
                    "totalContacts": r.total_contacts,
                    "createdAt": r.created_at.isoformat() if r.created_at else None,
                }
                for r in result.scalars().all()
            ]
        }


@router.post("/api/contacts/lists")
async def create_contact_list(
    body: CreateListBody,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.campaigns.write")
    factory = get_session_factory()
    if not factory:
        raise HTTPException(status_code=503, detail="Database not configured")

    list_id = uuid.uuid4()
    async with factory() as session:
        cl = ContactList(
            id=list_id,
            tenant_id=ctx.workspace_tenant_id,
            name=body.name.strip(),
            description=body.description,
            total_contacts=len(body.contacts),
        )
        session.add(cl)

        for c in body.contacts:
            phone = str(c.get("phone") or c.get("phone_e164") or "").strip()
            if not phone:
                continue
            session.add(
                Contact(
                    id=uuid.uuid4(),
                    tenant_id=ctx.workspace_tenant_id,
                    contact_list_id=list_id,
                    phone=phone,
                    first_name=c.get("first_name"),
                    last_name=c.get("last_name"),
                    full_name=c.get("full_name"),
                    email=c.get("email"),
                    company=c.get("company"),
                    job_title=c.get("job_title"),
                    country=c.get("country"),
                    city=c.get("city"),
                    state=c.get("state"),
                    timezone=c.get("timezone"),
                    notes=c.get("notes"),
                    custom_fields=c.get("custom_fields") or {},
                    raw_data=c.get("raw_data") or {},
                    source=c.get("source") or {},
                )
            )
        await session.commit()

    return {"ok": True, "listId": str(list_id), "totalContacts": len(body.contacts)}


@router.get("/api/contacts/lists/{list_id}/contacts")
async def get_list_contacts(
    list_id: str,
    ctx: ApiTenantContext = Depends(require_api_tenant),
):
    require_role_permission(ctx.role, "app.calls.read")
    factory = get_session_factory()
    if not factory:
        return {"contacts": []}
    async with factory() as session:
        # Enforce tenant isolation
        cl = await session.execute(
            select(ContactList).where(
                ContactList.id == uuid.UUID(list_id),
                ContactList.tenant_id == ctx.workspace_tenant_id,
            )
        )
        if not cl.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Contact list not found")

        result = await session.execute(
            select(Contact).where(
                Contact.contact_list_id == uuid.UUID(list_id),
                Contact.tenant_id == ctx.workspace_tenant_id,
            ).limit(200)
        )
        return {
            "contacts": [
                {
                    "id": str(r.id),
                    "phone": r.phone,
                    "firstName": r.first_name,
                    "lastName": r.last_name,
                    "fullName": r.full_name,
                    "email": r.email,
                    "company": r.company,
                    "customFields": r.custom_fields,
                }
                for r in result.scalars().all()
            ]
        }
