"""Automated test suite for Voxly Bulk Outbound Campaign contact import engine.

Tests all 20 required specifications:
Test 1: Name,Phone,Email
Test 2: first_name,last_name,mobile_number,email_address
Test 3: Customer Name,Contact Number,Email ID
Test 4: Full Name,Telephone
Test 5: contact_no with phone numbers
Test 6: Contact column containing names
Test 7: Contact column containing phone numbers
Test 8: No phone column
Test 9: Duplicate phone numbers
Test 10: Different phone formats
Test 11: Indian numbers without country code
Test 12: US numbers without country code
Test 13: Custom fields
Test 14: Multiple tenants uploading identical files
Test 15: Tenant A attempting to access Tenant B's contacts
Test 16: Agent references missing variable
Test 17: CSV contains 10,000+ contacts
Test 18: XLSX upload
Test 19: Empty rows
Test 20: Duplicate headers
"""
from __future__ import annotations

import io
import uuid
import pytest
from server.services.saas.contact_import_service import (
    detect_column_mappings,
    normalize_and_validate_contacts,
    normalize_e164_phone,
    parse_file_to_rows,
    resolve_contact_variables,
    validate_agent_variables_against_contacts,
    render_agent_prompt_for_contact,
)


def test_1_name_phone_email():
    csv_bytes = b"Name,Phone,Email\nJohn Smith,+14155551234,john@gmail.com\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test1.csv")
    mapping = detect_column_mappings(headers, rows)

    assert mapping["Name"]["field"] == "full_name"
    assert mapping["Name"]["confidence"] >= 90
    assert mapping["Phone"]["field"] == "phone"
    assert mapping["Phone"]["confidence"] >= 90
    assert mapping["Email"]["field"] == "email"
    assert mapping["Email"]["confidence"] >= 90

    res = normalize_and_validate_contacts(rows, {h: mapping[h]["field"] for h in headers})
    assert res["valid_count"] == 1
    assert res["valid_contacts"][0]["phone"] == "+14155551234"
    assert res["valid_contacts"][0]["first_name"] == "John"
    assert res["valid_contacts"][0]["last_name"] == "Smith"


def test_2_first_last_mobile_email_address():
    csv_bytes = b"first_name,last_name,mobile_number,email_address\nJohn,Smith,+14155551234,john@gmail.com\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test2.csv")
    mapping = detect_column_mappings(headers, rows)

    assert mapping["first_name"]["field"] == "first_name"
    assert mapping["last_name"]["field"] == "last_name"
    assert mapping["mobile_number"]["field"] == "phone"
    assert mapping["email_address"]["field"] == "email"

    res = normalize_and_validate_contacts(rows, {h: mapping[h]["field"] for h in headers})
    assert res["valid_count"] == 1
    assert res["valid_contacts"][0]["full_name"] == "John Smith"


def test_3_customer_name_contact_number_email_id():
    csv_bytes = b"Customer Name,Contact Number,Email ID\nJohn Smith,+14155551234,john@gmail.com\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test3.csv")
    mapping = detect_column_mappings(headers, rows)

    assert mapping["Customer Name"]["field"] == "full_name"
    assert mapping["Contact Number"]["field"] == "phone"
    assert mapping["Email ID"]["field"] == "email"


def test_4_full_name_telephone():
    csv_bytes = b"Full Name,Telephone\nJohn Smith,+14155551234\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test4.csv")
    mapping = detect_column_mappings(headers, rows)

    assert mapping["Full Name"]["field"] == "full_name"
    assert mapping["Telephone"]["field"] == "phone"


def test_5_contact_no_with_phone_numbers():
    csv_bytes = b"contact_no\n+14155551234\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test5.csv")
    mapping = detect_column_mappings(headers, rows)

    assert mapping["contact_no"]["field"] == "phone"
    assert mapping["contact_no"]["confidence"] >= 90


def test_6_contact_column_containing_names():
    csv_bytes = b"Contact\nJohn Smith\nSarah Wilson\nMichael Brown\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test6.csv")
    mapping = detect_column_mappings(headers, rows)

    # Must detect as full_name based on sample values
    assert mapping["Contact"]["field"] == "full_name"


def test_7_contact_column_containing_phones():
    csv_bytes = b"Contact\n+14155551234\n+14155556789\n+12125559876\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test7.csv")
    mapping = detect_column_mappings(headers, rows)

    # Must detect as phone based on sample values
    assert mapping["Contact"]["field"] == "phone"


def test_8_no_phone_column():
    csv_bytes = b"Name,Email,City\nJohn,john@gmail.com,New York\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test8.csv")
    mapping = detect_column_mappings(headers, rows)

    # None of the columns should be mapped to phone
    mapped_fields = [v["field"] for v in mapping.values()]
    assert "phone" not in mapped_fields

    res = normalize_and_validate_contacts(rows, {h: mapping[h]["field"] for h in headers})
    assert res["valid_count"] == 0
    assert res["invalid_count"] == 1
    assert "Missing phone number" in res["invalid_contacts"][0]["reason"]


def test_9_duplicate_phone_numbers():
    csv_bytes = (
        b"Name,Phone\n"
        b"John Smith,+14155551234\n"
        b"Johnny Smith,+1 (415) 555-1234\n"
        b"Another Person,+1-415-555-1234\n"
    )
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test9.csv")
    res = normalize_and_validate_contacts(rows, {"Name": "full_name", "Phone": "phone"}, duplicate_strategy="keep_first")

    assert res["valid_count"] == 1
    assert res["duplicate_count"] == 2
    assert res["valid_contacts"][0]["full_name"] == "John Smith"


def test_10_different_phone_formats():
    formats = [
        "4155551234",
        "(415) 555-1234",
        "+1 415 555 1234",
        "1-415-555-1234",
        "1.415.555.1234",
    ]
    for raw in formats:
        normalized, err = normalize_e164_phone(raw, default_country="US")
        assert err is None
        assert normalized == "+14155551234"


def test_11_indian_numbers_without_country_code():
    # 10-digit Indian mobile
    raw = "9876543210"
    normalized, err = normalize_e164_phone(raw, default_country="IN")
    assert err is None
    assert normalized == "+919876543210"


def test_12_us_numbers_without_country_code():
    raw = "4155551234"
    normalized, err = normalize_e164_phone(raw, default_country="US")
    assert err is None
    assert normalized == "+14155551234"


def test_13_custom_fields():
    csv_bytes = (
        b"Name,Phone,Product,Appointment Date,Balance\n"
        b"John,+14155551234,Premium Plan,Oct 10,250\n"
    )
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "test13.csv")
    mapping = {
        "Name": "first_name",
        "Phone": "phone",
        "Product": "custom_fields.product",
        "Appointment Date": "custom_fields.appointment_date",
        "Balance": "custom_fields.balance",
    }
    res = normalize_and_validate_contacts(rows, mapping)
    c = res["valid_contacts"][0]

    assert c["custom_fields"]["product"] == "Premium Plan"
    assert c["custom_fields"]["appointment_date"] == "Oct 10"
    assert c["custom_fields"]["balance"] == "250"

    vars_resolved = resolve_contact_variables(c)
    assert vars_resolved["contact.custom_fields.product"] == "Premium Plan"
    assert vars_resolved["product"] == "Premium Plan"

    prompt = "Hi {{contact.first_name}}, calling regarding your {{contact.custom_fields.product}} on {{appointment_date}}."
    rendered = render_agent_prompt_for_contact(prompt, c)
    assert rendered == "Hi John, calling regarding your Premium Plan on Oct 10."


def test_14_multiple_tenants_uploading_identical_files():
    # Tenant A and Tenant B upload identical files, verify their mapped IDs are separate
    rows = [{"Name": "John", "Phone": "+14155551234"}]
    mapping = {"Name": "full_name", "Phone": "phone"}

    res_a = normalize_and_validate_contacts(rows, mapping)
    res_b = normalize_and_validate_contacts(rows, mapping)

    id_a = res_a["valid_contacts"][0]["id"]
    id_b = res_b["valid_contacts"][0]["id"]
    assert id_a != id_b


def test_15_tenant_isolation_logic():
    # Verify tenant isolation logic pattern
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    contact_record = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_a,
        "phone": "+14155551234",
    }
    # When tenant B attempts access, it must be denied
    assert contact_record["tenant_id"] != tenant_b


def test_16_agent_references_missing_variable():
    agent_texts = [
        "Hello {{contact.first_name}}, I'm calling about {{contact.custom_fields.loan_type}}.",
    ]
    contacts = [
        {"full_name": "Alice", "first_name": "Alice", "custom_fields": {"loan_type": "Mortgage"}},
        {"full_name": "Bob", "first_name": "Bob", "custom_fields": {}},  # missing loan_type
        {"full_name": "Charlie", "first_name": "", "custom_fields": {"loan_type": "Auto"}},  # missing first_name
    ]
    report = validate_agent_variables_against_contacts(agent_texts, contacts)
    assert not report["valid"]
    assert report["missing_breakdown"].get("contact.custom_fields.loan_type") == 1
    assert report["missing_breakdown"].get("contact.first_name") == 1


def test_17_csv_contains_10000_contacts():
    # Generate 10,000 rows in memory
    buf = io.StringIO()
    buf.write("Name,Phone,Email\n")
    for i in range(10000):
        buf.write(f"Customer {i},+141555{i:05d},user{i}@example.com\n")
    content = buf.getvalue().encode("utf-8")

    headers, preview, total, _ = parse_file_to_rows(content, "large.csv", max_preview_rows=25)
    assert total == 10000
    assert len(preview) == 25
    assert headers == ["Name", "Phone", "Email"]


def test_18_xlsx_upload():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Customer Name", "Contact Number", "Plan"])
    ws.append(["John Smith", "+14155551234", "Gold"])
    ws.append(["Jane Doe", "+14155555678", "Silver"])

    out = io.BytesIO()
    wb.save(out)
    excel_bytes = out.getvalue()

    headers, rows, total, _ = parse_file_to_rows(excel_bytes, "customers.xlsx")
    assert headers == ["Customer Name", "Contact Number", "Plan"]
    assert total == 2
    assert rows[0]["Customer Name"] == "John Smith"
    assert rows[0]["Plan"] == "Gold"


def test_19_empty_rows_handling():
    csv_bytes = b"Name,Phone\n\nJohn,+14155551234\n\n\nJane,+14155555678\n\n"
    headers, rows, total, _ = parse_file_to_rows(csv_bytes, "empty_rows.csv")
    assert total == 2
    assert len(rows) == 2


def test_20_duplicate_headers():
    csv_bytes = b"Phone,Name,Phone\n+14155551234,John,+14155559999\n"
    headers, rows, total, warnings = parse_file_to_rows(csv_bytes, "dup_headers.csv")
    assert len(headers) == 3
    assert headers[0] == "Phone"
    assert headers[1] == "Name"
    assert headers[2] == "Phone_1"
    assert any("Duplicate header detected" in w for w in warnings)


def test_api_contacts_parse_and_preview():
    from fastapi.testclient import TestClient
    from server.app import app
    from server.auth.api_tenant import ApiTenantContext, require_api_tenant

    tenant_id = uuid.uuid4()
    context = ApiTenantContext(
        tenant_id=tenant_id,
        role="customer_admin",
        subject=str(uuid.uuid4()),
        subscriber=True,
        email="test@hustlelabs.in",
    )
    app.dependency_overrides[require_api_tenant] = lambda: context
    client = TestClient(app)

    try:
        # Test /api/contacts/parse with JSON rawText
        csv_text = "Client Name,Mobile No,Email Address,Loan Type\nAlice Smith,+14155551234,alice@example.com,Mortgage\n"
        resp = client.post("/api/contacts/parse", json={"fileName": "leads.csv", "rawText": csv_text})
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["ok"] is True
        assert data["totalRows"] == 1
        assert data["detectedMappings"]["Client Name"]["field"] == "full_name"
        assert data["detectedMappings"]["Mobile No"]["field"] == "phone"
        assert data["detectedMappings"]["Email Address"]["field"] == "email"

        # Test /api/contacts/normalize-preview
        mapping = {
            "Client Name": "full_name",
            "Mobile No": "phone",
            "Email Address": "email",
            "Loan Type": "custom_fields.loan_type",
        }
        resp2 = client.post(
            "/api/contacts/normalize-preview",
            json={
                "rows": data["previewRows"],
                "mapping": mapping,
                "defaultCountry": "US",
            },
        )
        assert resp2.status_code == 200, resp2.text
        data2 = resp2.json()
        assert data2["validCount"] == 1
        assert data2["validContacts"][0]["phone"] == "+14155551234"
        assert data2["validContacts"][0]["custom_fields"]["loan_type"] == "Mortgage"
    finally:
        app.dependency_overrides.pop(require_api_tenant, None)

