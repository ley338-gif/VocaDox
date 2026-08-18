from __future__ import annotations

import hashlib
import uuid

import pytest
from app.media.models import MediaKind, MediaSourceType
from app.media.service import bytes_to_chunks, ingest_media, spool_upload
from app.media.validation import UploadValidationError
from app.providers.storage import LocalFilesystemStorage

from tests.conversations.conftest import make_wav_bytes


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path / "media-root")


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path / "tmp-uploads"


async def test_spool_upload_rejects_empty_file(temp_dir) -> None:
    with pytest.raises(UploadValidationError):
        await spool_upload(bytes_to_chunks(b""), temp_dir=temp_dir, max_size_bytes=10_000)


async def test_spool_upload_rejects_oversize(temp_dir) -> None:
    data = b"RIFF" + b"\x00" * 100
    with pytest.raises(UploadValidationError):
        await spool_upload(bytes_to_chunks(data), temp_dir=temp_dir, max_size_bytes=10)


async def test_spool_upload_computes_sha256(temp_dir) -> None:
    data = make_wav_bytes()
    spooled = await spool_upload(
        bytes_to_chunks(data), temp_dir=temp_dir, max_size_bytes=10_000_000
    )
    assert spooled.sha256 == hashlib.sha256(data).hexdigest()
    assert spooled.size_bytes == len(data)
    spooled.path.unlink()


async def test_ingest_media_persists_sha256_and_is_immutable(db_session, storage, temp_dir) -> None:
    data = make_wav_bytes(duration_s=0.5)
    original_sha256 = hashlib.sha256(data).hexdigest()
    spooled = await spool_upload(
        bytes_to_chunks(data), temp_dir=temp_dir, max_size_bytes=10_000_000
    )

    conversation_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()

    media = await ingest_media(
        db_session,
        spooled=spooled,
        conversation_id=conversation_id,
        organization_id=organization_id,
        kind=MediaKind.SOURCE_AUDIO,
        source_type=MediaSourceType.FILE_UPLOAD,
        original_filename="test.wav",
        created_by_user_id=user_id,
        storage=storage,
    )

    assert media.sha256 == original_sha256
    assert media.size_bytes == len(data)
    assert media.container == "wav"
    assert media.content_type == "audio/wav"
    assert media.duration_ms is not None and media.duration_ms > 0
    assert media.sample_rate == 8000
    assert media.channels == 1

    # Source bytes on disk are byte-for-byte identical to what was ingested
    # — the defining "immutable source" property.
    stored = await storage.load(media.storage_key)
    assert hashlib.sha256(stored).hexdigest() == original_sha256

    # The storage key encodes the conceptual org/conversation/kind layout
    # but stays an opaque key — never a raw filesystem path.
    assert f"organizations/{organization_id.hex}" in media.storage_key
    assert f"conversations/{conversation_id.hex}" in media.storage_key
    assert "/source/" in media.storage_key


async def test_ingest_media_rejects_unrecognized_format(db_session, storage, temp_dir) -> None:
    data = b"this is not an audio file, just text" * 5
    spooled = await spool_upload(
        bytes_to_chunks(data), temp_dir=temp_dir, max_size_bytes=10_000_000
    )

    with pytest.raises(UploadValidationError):
        await ingest_media(
            db_session,
            spooled=spooled,
            conversation_id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            kind=MediaKind.SOURCE_AUDIO,
            source_type=MediaSourceType.FILE_UPLOAD,
            original_filename="fake.wav",
            created_by_user_id=uuid.uuid4(),
            storage=storage,
        )
    # Rejected upload must not leave a temp file behind.
    assert not spooled.path.exists()


async def test_ingest_media_handles_a_larger_synthetic_file(db_session, storage, temp_dir) -> None:
    """Performance smoke test: a several-MB synthetic WAV, streamed through
    spool_upload + ingest_media, to catch whole-file-in-memory mistakes or
    obvious upload-limit errors. Not a claim of enterprise-scale
    performance — just a sanity check the streaming path actually streams."""
    data = make_wav_bytes(duration_s=30.0, sample_rate=44100)
    assert len(data) > 2_000_000  # a few MB, not the toy 0.2s fixtures used elsewhere
    spooled = await spool_upload(
        bytes_to_chunks(data), temp_dir=temp_dir, max_size_bytes=50_000_000
    )
    media = await ingest_media(
        db_session,
        spooled=spooled,
        conversation_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        kind=MediaKind.SOURCE_AUDIO,
        source_type=MediaSourceType.FILE_UPLOAD,
        original_filename="long-session.wav",
        created_by_user_id=uuid.uuid4(),
        storage=storage,
    )
    assert media.size_bytes == len(data)
    assert media.duration_ms is not None and 29_000 <= media.duration_ms <= 31_000


async def test_ingest_media_never_reuses_a_client_supplied_path(
    db_session, storage, temp_dir
) -> None:
    """The original filename must never become (part of) the storage key —
    only server-generated UUID segments do."""
    data = make_wav_bytes()
    spooled = await spool_upload(
        bytes_to_chunks(data), temp_dir=temp_dir, max_size_bytes=10_000_000
    )
    media = await ingest_media(
        db_session,
        spooled=spooled,
        conversation_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        kind=MediaKind.SOURCE_AUDIO,
        source_type=MediaSourceType.FILE_UPLOAD,
        original_filename="../../../etc/passwd",
        created_by_user_id=uuid.uuid4(),
        storage=storage,
    )
    assert "passwd" not in media.storage_key
    assert ".." not in media.storage_key
