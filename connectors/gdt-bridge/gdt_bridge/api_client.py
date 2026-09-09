"""Thin httpx wrapper for VocaDox's Integration API
(`/api/v1/integrations/api/...`, service-account Bearer auth). No
precedent existed in the VocaDox repo for an external client calling
VocaDox's own API before this connector -- see ADR-0041."""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class ApiError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"VocaDox API error {status_code}: {detail}")
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class ExportedFile:
    content: bytes
    media_type: str
    filename: str


class VocaDoxClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> VocaDoxClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def list_conversations(self) -> list[dict]:
        """Cheap, `conversation:read`-scoped call used by the CLI's
        `test-connection` command to verify `base_url`/`api_key` without
        requiring any particular write scope to be granted."""
        resp = await self._client.get("/api/v1/integrations/api/conversations")
        _raise_for_status(resp)
        return resp.json()

    async def create_conversation(
        self, *, title: str, external_reference: str | None, external_reference_type: str | None
    ) -> str:
        resp = await self._client.post(
            "/api/v1/integrations/api/conversations",
            json={
                "title": title,
                "external_reference": external_reference,
                "external_reference_type": external_reference_type,
            },
        )
        _raise_for_status(resp)
        return resp.json()["id"]

    async def create_patient_participant(self, conversation_id: str, *, display_name: str) -> None:
        resp = await self._client.post(
            f"/api/v1/integrations/api/conversations/{conversation_id}/participants",
            json={"display_name": display_name, "participant_type": "patient"},
        )
        _raise_for_status(resp)

    async def get_document_status(self, conversation_id: str) -> str | None:
        """Returns the current revision's status (e.g. `"approved"`), or
        `None` if no document has been composed yet."""
        resp = await self._client.get(
            f"/api/v1/integrations/api/conversations/{conversation_id}/document"
        )
        if resp.status_code == 404:
            return None
        _raise_for_status(resp)
        payload = resp.json()
        revision = payload.get("current_revision")
        return revision["status"] if revision else None

    async def export_document(self, conversation_id: str, *, format: str) -> ExportedFile:  # noqa: A002
        resp = await self._client.get(
            f"/api/v1/integrations/api/conversations/{conversation_id}/document/export",
            params={"format": format},
        )
        _raise_for_status(resp)
        content_disposition = resp.headers.get("content-disposition", "")
        filename = _filename_from_content_disposition(content_disposition) or f"{conversation_id}.bin"
        return ExportedFile(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            filename=filename,
        )


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise ApiError(resp.status_code, str(detail))


def _filename_from_content_disposition(header: str) -> str | None:
    marker = 'filename="'
    start = header.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = header.find('"', start)
    return header[start:end] if end != -1 else None
