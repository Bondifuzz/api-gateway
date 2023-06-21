import logging
from asyncio import CancelledError
from contextlib import AsyncExitStack
from io import BytesIO
from typing import TYPE_CHECKING, AsyncIterator, Optional

from aiobotocore.response import StreamingBody as StreamingResponse

# from aiohttp import ClientError
from botocore.exceptions import ClientError, HTTPClientError

from .errors import (
    ObjectNotFoundError,
    ObjectStorageError,
    UploadLimitError,
    maybe_not_found,
    maybe_unknown_error,
)
from .initializer import ObjectStorageInitializer
from .paths import BucketData, BucketFuzzers

if TYPE_CHECKING:
    from aioboto3_hints.s3.client import Client as S3Client
    from aioboto3_hints.s3.service_resource import ServiceResource as S3Resource
else:
    S3Resource = object
    S3Client = object


class AsyncStreamingBody:

    _chunks: AsyncIterator[bytes]
    _backlog: bytes

    def __init__(self, chunks: AsyncIterator[bytes]):
        self._chunks = chunks
        self._backlog = b""

    async def _read_until_end(self):

        content = self._backlog
        self._backlog = b""

        while True:
            try:
                content += await self._chunks.__anext__()
            except StopAsyncIteration:
                break

        return content

    async def _read_chunk(self, size: int):

        content = self._backlog
        bytes_read = len(self._backlog)

        while bytes_read < size:

            try:
                chunk = await self._chunks.__anext__()
            except StopAsyncIteration:
                break

            content += chunk
            bytes_read += len(chunk)

        self._backlog = content[size:]
        content = content[:size]

        return content

    async def read(self, size: int = -1):
        if size > 0:
            return await self._read_chunk(size)
        elif size == -1:
            return await self._read_until_end()
        else:
            return b""


class StreamingUpload:

    _body: AsyncStreamingBody
    _limit: int
    _total: int

    def __init__(self, chunks: AsyncIterator[bytes], limit: int):
        self._body = AsyncStreamingBody(chunks)
        self._limit = limit
        self._total = 0

    async def read(self, size: int = -1):

        bytes_read = await self._body.read(size)
        self._total += len(bytes_read)

        if self._total > self._limit:
            raise UploadLimitError()

        return bytes_read

    def is_limit_reached(self):
        return self._total > self._limit


async def streaming_download(s3_object, chunk_size=4096):

    stream: StreamingResponse
    async with s3_object["Body"] as stream:
        while True:
            data = await stream.read(chunk_size)
            if not data:
                return
            yield data


class ObjectStorage:

    _s3: S3Resource
    _client: S3Client
    _context_stack: Optional[AsyncExitStack]
    _logger: logging.Logger
    _is_closed: bool

    _bucket_fuzzers: BucketFuzzers
    _bucket_data: BucketData

    async def _init(self, settings):

        self._is_closed = True
        self._context_stack = None
        self._logger = logging.getLogger("s3")

        initializer = await ObjectStorageInitializer.create(settings)
        await initializer.do_init()

        self._s3 = initializer.s3
        self._client = initializer.s3.meta.client
        self._context_stack = initializer.context_stack
        self._bucket_fuzzers = initializer.bucket_fuzzers
        self._bucket_data = initializer.bucket_data
        self._is_closed = False

    @staticmethod
    async def create(settings):
        _self = ObjectStorage()
        await _self._init(settings)
        return _self

    async def close(self):

        assert not self._is_closed, "ObjectStorage connection has been already closed"

        if self._context_stack:
            await self._context_stack.aclose()
            self._context_stack = None

        self._is_closed = True

    def __del__(self):
        if not self._is_closed:
            self._logger.error("ObjectStorage connection has not been closed")

    @maybe_unknown_error
    async def _streaming_upload(
        self,
        chunks: AsyncIterator[bytes],
        bucket_name: str,
        object_key: str,
        upload_limit: int,
    ):
        assert upload_limit > 0
        stream = StreamingUpload(chunks, upload_limit)

        try:
            await self._client.upload_fileobj(stream, bucket_name, object_key)
        except HTTPClientError as e:
            error = e.kwargs.get("error")
            if isinstance(error, CancelledError):
                if stream.is_limit_reached():
                    raise UploadLimitError() from e
            raise

    @maybe_unknown_error
    async def _upload(
        self,
        content: bytes,
        bucket_name: str,
        object_key: str,
    ):
        stream = BytesIO(content)
        await self._client.upload_fileobj(stream, bucket_name, object_key)

    @maybe_unknown_error
    @maybe_not_found
    async def _streaming_download(
        self,
        bucket_name: str,
        object_key: str,
    ):
        obj = await self._client.get_object(Bucket=bucket_name, Key=object_key)
        return streaming_download(obj)

    @maybe_unknown_error
    @maybe_not_found
    async def _download(
        self,
        bucket_name: str,
        object_key: str,
    ):
        stream = BytesIO()
        downloader = await self._streaming_download(bucket_name, object_key)

        async for chunk in downloader:
            stream.write(chunk)

        return stream.getvalue()

    async def upload_fuzzer_config(
        self,
        fuzzer_id: str,
        fuzzer_rev: str,
        config: bytes,
    ):
        bucket, key = self._bucket_fuzzers.config(fuzzer_id, fuzzer_rev)
        await self._upload(config, bucket, key)

    async def download_fuzzer_config(self, fuzzer_id: str, fuzzer_rev: str) -> bytes:
        bucket, key = self._bucket_fuzzers.config(fuzzer_id, fuzzer_rev)
        return await self._download(bucket, key)

    async def upload_fuzzer_binaries(
        self,
        fuzzer_id: str,
        fuzzer_rev: str,
        chunks: AsyncIterator[bytes],
        upload_limit: int,
    ):
        bucket, key = self._bucket_fuzzers.binaries(fuzzer_id, fuzzer_rev)
        await self._streaming_upload(chunks, bucket, key, upload_limit)

    async def download_fuzzer_binaries(self, fuzzer_id: str, fuzzer_rev: str):
        bucket, key = self._bucket_fuzzers.binaries(fuzzer_id, fuzzer_rev)
        return await self._streaming_download(bucket, key)

    async def upload_fuzzer_seeds(
        self,
        fuzzer_id: str,
        fuzzer_rev: str,
        chunks: AsyncIterator[bytes],
        upload_limit: int = 0,
    ):
        bucket, key = self._bucket_fuzzers.seeds(fuzzer_id, fuzzer_rev)
        await self._streaming_upload(chunks, bucket, key, upload_limit)

    async def download_fuzzer_seeds(self, fuzzer_id: str, fuzzer_rev: str):
        bucket, key = self._bucket_fuzzers.seeds(fuzzer_id, fuzzer_rev)
        return await self._streaming_download(bucket, key)

    async def download_crash(self, fuzzer_id: str, fuzzer_rev: str, input_id: str):
        bucket, key = self._bucket_data.crash(fuzzer_id, fuzzer_rev, input_id)
        return await self._streaming_download(bucket, key)

    async def download_fuzzer_corpus(self, fuzzer_id: str, fuzzer_rev: str):
        bucket, key = self._bucket_data.merged_corpus(fuzzer_id, fuzzer_rev)
        return await self._streaming_download(bucket, key)

    async def copy_corpus_files(
        self,
        src_fuzzer_rev: str,
        dst_fuzzer_rev: str,
        parent_fuzzer_id: str,
    ):
        src_bucket, src_key = self._bucket_data.merged_corpus(
            parent_fuzzer_id, src_fuzzer_rev
        )

        dst_bucket, dst_key = self._bucket_data.merged_corpus(
            parent_fuzzer_id, dst_fuzzer_rev
        )

        try:
            copy_source = {"Bucket": src_bucket, "Key": src_key}
            await self._client.copy(copy_source, dst_bucket, dst_key)

        except ClientError as e:

            if e.response["Error"]["Code"] == "404":
                msg = f"Object not found <bucket={src_bucket}, key={src_key}>"
                raise ObjectNotFoundError(msg) from e

            raise ObjectStorageError(str(e))
