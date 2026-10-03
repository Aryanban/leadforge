import pytest
import io
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_leads_csv_import_and_export():
    csv_data = (
        "Business Name,Phone,Email,Website,Address,Industry\n"
        "Skyline Estates,+919876543210,info@skylineestates.in,https://skylineestates.in,Sector 15 Rohini,Real Estate\n"
        "Metro Dental Clinic,+919811122233,dr.arora@metrodental.com,https://metrodental.com,Pitampura Delhi,Dentist\n"
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Test CSV import
        resp = await ac.post("/api/v1/leads/import/csv", json={"csv_content": csv_data})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["imported"] == 2

        # Test CSV export
        export_resp = await ac.get("/api/v1/leads/export/csv")
        assert export_resp.status_code == 200
        assert "text/csv" in export_resp.headers["content-type"]
        assert "Skyline Estates" in export_resp.text

        # Test Spam checker endpoint
        spam_resp = await ac.post("/api/v1/campaigns/check-spam", json={
            "subject": "Quick question for {{business_name}}",
            "body": "Hi {{first_name}}, saw your work and wanted to connect."
        })
        assert spam_resp.status_code == 200
        spam_data = spam_resp.json()
        assert spam_data["is_safe"] is True
        assert spam_data["score"] >= 80

        # Test Twenty CRM export endpoint
        crm_resp = await ac.get("/api/v1/leads/export/twenty-crm")
        assert crm_resp.status_code == 200
        crm_data = crm_resp.json()
        assert "companies" in crm_data
        assert crm_data["source"] == "leadforge"
