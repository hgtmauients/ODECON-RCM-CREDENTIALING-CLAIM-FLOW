from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.clearinghouse_transport import SFTPTransport


@pytest.mark.security
@pytest.mark.asyncio
async def test_download_files_sanitizes_remote_filename_and_enforces_tenant_root(monkeypatch, tmp_path):
    monkeypatch.setenv("EDI_DOWNLOAD_PATH", str(tmp_path))
    monkeypatch.setattr("services.clearinghouse_transport.assert_safe_sftp_host", lambda *_args, **_kwargs: None)

    ssh = MagicMock()
    sftp = MagicMock()
    ssh.open_sftp.return_value = sftp
    sftp.listdir.return_value = ["../evil.835", "safe.835"]
    monkeypatch.setattr(SFTPTransport, "_build_ssh_client", staticmethod(lambda: ssh))

    db = AsyncMock()
    tenant_result = MagicMock()
    tenant_result.scalar_one_or_none.return_value = "00000000-0000-0000-0000-0000000000a1"
    db.execute.return_value = tenant_result

    connection = SimpleNamespace(
        payer_id=11,
        sftp_password_encrypted=None,
        sftp_host="test.example.com",
        sftp_port=22,
        sftp_username="uploader",
        sftp_inbound_path="/inbound",
    )

    transport = SFTPTransport(db)
    files = await transport.download_files(connection, file_pattern="*.835")

    assert len(files) == 2

    expected_root = (tmp_path / "00000000-0000-0000-0000-0000000000a1").resolve()
    for row in files:
        local_path = Path(row["local_path"]).resolve()
        local_path.relative_to(expected_root)

    first_local = Path(files[0]["local_path"]).name
    second_local = Path(files[1]["local_path"]).name
    assert first_local == "evil.835"
    assert second_local == "safe.835"

    first_remote, first_local_path = sftp.get.call_args_list[0].args
    second_remote, second_local_path = sftp.get.call_args_list[1].args
    assert first_remote == "/inbound/../evil.835"
    assert second_remote == "/inbound/safe.835"
    Path(first_local_path).resolve().relative_to(expected_root)
    Path(second_local_path).resolve().relative_to(expected_root)
