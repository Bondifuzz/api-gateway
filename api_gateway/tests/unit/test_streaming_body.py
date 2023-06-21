import pytest

from api_gateway.app.object_storage.storage import AsyncStreamingBody


class AsyncGen:

    """Async data generator. Generates N data blocks with length of L"""

    def __init__(self, block_count, block_size) -> None:
        self.bc = block_count
        self.bs = block_size

    def __aiter__(self):
        return self

    async def __anext__(self):

        if self.bc == 0:
            raise StopAsyncIteration()

        self.bc -= 1
        return b"A" * self.bs


@pytest.mark.asyncio()
@pytest.mark.parametrize("bc", range(10))
@pytest.mark.parametrize("bs", range(10))
async def test_streaming_body_read_full(bs, bc):

    """
    Description
        Try to read all data from provided
        chunks with different sizes

    Succeeds
        If number of bytes read is correct
    """

    n = 1000
    async_gen = AsyncGen(bc, bs * n)
    body = AsyncStreamingBody(async_gen)
    res = await body.read()
    assert len(res) == bc * bs * n


@pytest.mark.asyncio()
@pytest.mark.parametrize("bc", range(10))
@pytest.mark.parametrize("bs", range(10))
async def test_streaming_body_read_n_full(bs, bc):

    """
    Description
        Try to read all n bytes of data from
        provided chunks with different sizes

    Succeeds
        If number of bytes read is correct
    """

    n = 1000
    async_gen = AsyncGen(bc, bs * n)
    body = AsyncStreamingBody(async_gen)
    res = await body.read(bc * bs * n)
    assert len(res) == bc * bs * n


@pytest.mark.asyncio()
@pytest.mark.parametrize("n", range(100))
async def test_streaming_body_read_partial(n):

    """
    Description
        Try to read 0..999 bytes of data from generator

    Succeeds
        If number of bytes read is correct
    """

    async_gen = AsyncGen(1, 500500)
    body = AsyncStreamingBody(async_gen)

    for i in range(n):
        res = await body.read(i)
        assert len(res) == i


@pytest.mark.asyncio()
async def test_streaming_body_read_full_partial_eof():

    """
    Description
        Try to read all data and then call read again

    Succeeds
        If number of bytes read is correct
    """

    n = 10000
    async_gen = AsyncGen(1, n)
    body = AsyncStreamingBody(async_gen)

    res = await body.read()
    assert len(res) == n

    res = await body.read(1)
    assert len(res) == 0


@pytest.mark.asyncio()
async def test_streaming_body_read_full_full_eof():

    """
    Description
        Try to read all data and then call read again

    Succeeds
        If number of bytes read is correct
    """

    n = 10000
    async_gen = AsyncGen(1, n)
    body = AsyncStreamingBody(async_gen)

    res = await body.read()
    assert len(res) == n

    res = await body.read()
    assert len(res) == 0


@pytest.mark.asyncio()
async def test_streaming_body_read_partial_full_eof():

    """
    Description
        Try to read all data and then call read again

    Succeeds
        If number of bytes read is correct
    """

    n = 10000
    async_gen = AsyncGen(1, n)
    body = AsyncStreamingBody(async_gen)

    res = await body.read(n)
    assert len(res) == n

    res = await body.read()
    assert len(res) == 0


@pytest.mark.asyncio()
@pytest.mark.parametrize("i", range(100))
async def test_streaming_body_read_until_end(i):

    """
    Description
        Try to read n bytes an then
        read until the end of data

    Succeeds
        If number of bytes read is correct
    """

    n = 100
    async_gen = AsyncGen(1, n)
    body = AsyncStreamingBody(async_gen)

    res = await body.read(i)
    assert len(res) == i

    res = await body.read()
    assert len(res) == n - i
