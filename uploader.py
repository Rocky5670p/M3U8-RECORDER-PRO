import aiohttp
import os
import time

from config import BOT_TOKEN, UPLOAD_CHUNK_SIZE


class UploadCancelled(Exception):
    pass


async def upload_document(
    chat_id,
    file_path,
    caption,
    progress_callback=None,
    cancel_event=None
):

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendDocument"
    )

    file_size = os.path.getsize(file_path)

    sent = 0
    started = time.time()

    class AsyncFile:

        def __init__(self, path):

            self.file = open(
                path,
                "rb"
            )

        async def read(self):

            nonlocal sent

            if (
                cancel_event and
                cancel_event.is_set()
            ):

                self.file.close()

                raise UploadCancelled()

            chunk = self.file.read(
                UPLOAD_CHUNK_SIZE
            )

            if not chunk:

                self.file.close()

                return b""

            sent += len(chunk)

            if progress_callback:

                elapsed = (
                    time.time() -
                    started
                )

                speed = (
                    sent / elapsed
                    if elapsed > 0
                    else 0
                )

                percent = (
                    sent /
                    file_size
                ) * 100

                await progress_callback(
                    percent,
                    sent,
                    file_size,
                    speed
                )

            return chunk

    class StreamPayload(
        aiohttp.payload.AsyncIterablePayload
    ):

        def __init__(self, source):

            async def iterator():

                while True:

                    chunk = await source.read()

                    if not chunk:
                        break

                    yield chunk

            super().__init__(
                iterator(),
                content_type="application/octet-stream"
            )

    source = AsyncFile(file_path)

    form = aiohttp.FormData()

    form.add_field(
        "chat_id",
        str(chat_id)
    )

    form.add_field(
        "caption",
        caption
    )

    form.add_field(
        "document",
        StreamPayload(source),
        filename=os.path.basename(file_path),
        content_type="application/octet-stream"
    )

    timeout = aiohttp.ClientTimeout(
        total=None,
        sock_connect=60,
        sock_read=300
    )

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.post(
            url,
            data=form
        ) as response:

            data = await response.json()

            if not data.get("ok"):

                raise RuntimeError(
                    str(data)
                )

            return data