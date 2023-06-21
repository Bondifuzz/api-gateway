import io
import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING

import aioboto3
from aiohttp.client_exceptions import ClientConnectionError
from botocore.exceptions import ClientError

from api_gateway.app.settings import AppSettings

from .errors import ObjectStorageError
from .paths import BucketData, BucketFuzzers

if TYPE_CHECKING:
    from aioboto3_hints.s3.service_resource import ServiceResource as S3Resource
else:
    S3Resource = object


########################################
# Object Storage Base Initializer
########################################


class ObjectStorageBaseInitializer:

    _s3: S3Resource
    _context_stack: AsyncExitStack

    def get_logger(self):
        return logging.getLogger("s3.init")

    async def _verify_auth(self):
        try:
            await self._s3.meta.client.list_buckets()
        except ClientConnectionError as e:
            raise ObjectStorageError(str(e)) from e
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "InvalidAccessKeyId":
                raise ObjectStorageError(f"Invalid access key") from e
            elif error_code == "SignatureDoesNotMatch":
                raise ObjectStorageError(f"Invalid secret key") from e
            else:
                raise ObjectStorageError(str(e)) from e

    async def _check_bucket_exists(self, bucket_name):
        try:
            await self._s3.meta.client.head_bucket(Bucket=bucket_name)
        except ClientError as e:
            error_code = e.response["ResponseMetadata"]["HTTPStatusCode"]
            if error_code == 404:
                raise ObjectStorageError(
                    f"Bucket '{bucket_name}' does not exist"
                ) from e
            elif error_code == 403:
                raise ObjectStorageError(
                    f"Not enough rights to read bucket '{bucket_name}'"
                ) from e
            else:
                raise ObjectStorageError(str(e)) from e

    async def _check_for_read_permissions(self, bucket_name):

        """
        Check bucket read access in two steps:
        1) Try to list objects in bucket.
        2) Try to download file. No access -> will get 403 first
        """

        try:
            await self._s3.meta.client.list_objects(Bucket=bucket_name, MaxKeys=1)

            try:
                f = io.BytesIO()
                await self._s3.meta.client.download_fileobj(bucket_name, "test_read", f)

            except ClientError as e:
                if int(e.response["Error"]["Code"]) != 404:
                    raise

            finally:
                f.close()

        except ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] == 403:
                raise ObjectStorageError(
                    f"Not enough rights to read contents of bucket '{bucket_name}'"
                ) from e
            else:
                raise ObjectStorageError(
                    f"Failed to read contents of bucket '{bucket_name}'. {str(e)}"
                ) from e

    async def _check_for_write_permissions(self, bucket_name):

        bucket = await self._s3.Bucket(bucket_name)
        obj = await bucket.Object("mykey")

        try:
            await obj.upload_fileobj(io.BytesIO(b"write-test"))
            await obj.delete()

        except ClientError as e:
            if e.response["ResponseMetadata"]["HTTPStatusCode"] == 403:
                raise ObjectStorageError(
                    f"Not enough rights to write to bucket '{bucket_name}'"
                ) from e
            else:
                raise ObjectStorageError(
                    f"Failed to write to bucket '{bucket_name}'. {str(e)}"
                ) from e

    async def _check_bucket(self, name, check_read, check_write):

        logger = self.get_logger()
        logger.info("Checking bucket '%s'", name)
        logger.info("Required permissions: read=%s, write=%s", check_read, check_write)

        await self._check_bucket_exists(name)

        logger.info("Bucket '%s' exists. Checking permissions...", name)

        if check_read:
            await self._check_for_read_permissions(name)

        if check_write:
            await self._check_for_write_permissions(name)

    def get_init_tasks(self):
        yield "Authentication", self._verify_auth()

    async def do_init(self):

        logger = self.get_logger()

        try:
            logger.info("Initializing object storage...")
            for name, task in self.get_init_tasks():
                logger.info("Performing '%s'", name)
                await task

            logger.info("Initializing object storage... OK")

        except:
            await self._context_stack.aclose()
            raise

    async def _create_resource(self, **kwargs):
        try:
            # aioboto 9.0.0+
            session = aioboto3.Session()
            resource = session.resource(**kwargs)
        except AttributeError:
            # aioboto 8.X.X and older
            resource = aioboto3.resource(**kwargs)

        context_stack = AsyncExitStack()
        resource = await context_stack.enter_async_context(resource)

        return resource, context_stack

    async def _init(self, settings: AppSettings):

        logger = self.get_logger()
        endpoint_url = settings.object_storage.url
        access_key = settings.object_storage.access_key
        secret_key = settings.object_storage.secret_key

        logger.info("Using access key '%s'", access_key)
        resource, context_stack = await self._create_resource(
            service_name="s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

        self._s3 = resource
        self._context_stack = context_stack

    @staticmethod
    async def create(settings):
        _self = ObjectStorageBaseInitializer()
        await _self._init(settings)
        return _self

    @property
    def s3(self):
        return self._s3

    @property
    def context_stack(self):
        return self._context_stack


########################################
# Object Storage Initializer
########################################


class ObjectStorageInitializer(ObjectStorageBaseInitializer):

    _bucket_fuzzers: BucketFuzzers
    _bucket_data: BucketData

    async def _check_bucket_fuzzers(self):
        name = self._bucket_fuzzers.name
        await self._check_bucket(name, check_read=True, check_write=True)

    async def _check_bucket_data(self):
        name = self._bucket_data.name
        await self._check_bucket(name, check_read=True, check_write=False)

    def get_init_tasks(self):
        yield from super().get_init_tasks()
        yield "Check <fuzzers> bucket", self._check_bucket_fuzzers()
        yield "Check <data> bucket", self._check_bucket_data()

    async def _init(self, settings: AppSettings):
        await super()._init(settings)
        buckets = settings.object_storage.buckets
        self._bucket_fuzzers = BucketFuzzers(buckets.fuzzers)
        self._bucket_data = BucketData(buckets.data)

    @staticmethod
    async def create(settings):
        _self = ObjectStorageInitializer()
        await _self._init(settings)
        return _self

    @property
    def bucket_fuzzers(self):
        return self._bucket_fuzzers

    @property
    def bucket_data(self):
        return self._bucket_data
