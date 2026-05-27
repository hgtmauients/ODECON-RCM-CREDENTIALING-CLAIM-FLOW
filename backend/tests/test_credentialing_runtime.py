from services.credentialing_runtime import _collect_associated_licenses, _merge_state_license_with_caqh


def test_collect_associated_licenses_merges_and_dedupes():
    api_cert_result = {
        "associated_licenses": [
            {"state": "HI", "license_number": "MD-21277", "status": "ACTIVE", "expiration_date": "2030-01-01"},
            {"state": "CA", "license_number": "A12345", "status": "ACTIVE", "expiration_date": "2028-05-01"},
        ],
        "matches": [
            {"state": "HI", "license_number": "MD-21277", "status": "ACTIVE", "expiration_date": "2030-01-01"},
        ],
    }
    prior_state = {
        "licenses": [
            {"state": "NV", "license_number": "NV-999", "status": "EXPIRED", "expiration_date": "2020-01-01"},
        ]
    }

    out = _collect_associated_licenses(api_cert_result=api_cert_result, prior_state_license=prior_state)
    assert len(out) == 3
    assert out[0]["license_number"] == "MD-21277"
    assert out[1]["license_number"] == "A12345"
    assert out[2]["license_number"] == "NV-999"


def test_merge_state_license_with_caqh_backfills_expiration_and_associated():
    base = {
        "verified": True,
        "state": "HI",
        "license_number": "MD-21277",
        "status": "ACTIVE",
        "expiration_date": None,
        "associated_licenses": [{"state": "HI", "license_number": "MD-21277", "status": "ACTIVE", "expiration_date": ""}],
    }
    caqh = [
        {"state": "HI", "license_number": "MD-21277", "status": "ACTIVE", "issue_date": "2018-01-01", "expiration_date": "2029-12-31"},
        {"state": "CA", "license_number": "A12345", "status": "ACTIVE", "issue_date": "2020-01-01", "expiration_date": "2028-01-01"},
    ]

    merged = _merge_state_license_with_caqh(
        state_license_verification=base,
        caqh_licenses=caqh,
        state_code="HI",
        preferred_license_number="MD-21277",
    )

    assert merged["expiration_date"] == "2029-12-31"
    assert merged["issue_date"] == "2018-01-01"
    assert len(merged["associated_licenses"]) == 2


def test_merge_state_license_with_caqh_creates_when_missing():
    merged = _merge_state_license_with_caqh(
        state_license_verification={},
        caqh_licenses=[
            {"state": "HI", "license_number": "MD-21277", "status": "ACTIVE", "expiration_date": "2030-01-01"}
        ],
        state_code="HI",
        preferred_license_number="",
    )
    assert merged["verified"] is True
    assert merged["source"] == "caqh_proview"
    assert merged["license_number"] == "MD-21277"
