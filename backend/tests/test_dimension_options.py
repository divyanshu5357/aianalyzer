import re
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_source_dimension_values_excludes_raw_phone_numbers():
    """Verify that dimension-values endpoint for source returns high-volume marketing channels and excludes raw phone numbers."""
    response = client.get("/api/dashboard/dimension-values?dimension=source")
    assert response.status_code == 200
    sources = response.json()
    assert len(sources) > 0, "Source dimension values should not be empty"

    # Top options must not be pure 10-12 digit phone numbers
    phone_pattern = re.compile(r"^\+?\d{10,12}$")
    top_options = sources[:10]
    for opt in top_options:
        assert not phone_pattern.match(opt), f"Source option '{opt}' is a raw phone number"

    # Must contain recognized top marketing channels
    valid_channels = {"Publisher-API", "Widget", "Google", "Website", "Meta", "Shiksha", "CollegeDekho", "Careers360", "Direct"}
    found_channels = set(sources).intersection(valid_channels)
    assert len(found_channels) > 0, f"Expected top channels in source options, found: {sources[:10]}"


def test_dashboard_options_sources_excludes_raw_phone_numbers():
    """Verify that dashboard options endpoint sources list excludes raw phone numbers."""
    response = client.get("/api/dashboard/options")
    assert response.status_code == 200
    data = response.json()
    sources = data.get("sources", [])
    assert len(sources) > 0, "Sources in options should not be empty"

    phone_pattern = re.compile(r"^\+?\d{10,12}$")
    top_options = sources[:10]
    for opt in top_options:
        assert not phone_pattern.match(opt), f"Source in options '{opt}' is a raw phone number"


def test_all_core_dimension_options():
    """Verify that all core analytical dimensions (source, state, owner, program_name) return valid options."""
    for dim in ["source", "state", "owner", "program_name"]:
        response = client.get(f"/api/dashboard/dimension-values?dimension={dim}")
        assert response.status_code == 200
        values = response.json()
        assert isinstance(values, list)
        assert len(values) > 0, f"Dimension '{dim}' returned empty options list"
