import asyncio
import os
import signal
from pathlib import Path

from config import RECORDINGS_DIR


class RecorderError(Exception):
    pass


class Recorder:

    def __init__(self, engine="ffmpeg"):

        self.engine = engine.lower()
        self.process = None

    async def start(
        self,
        url,
        output,
        duration,
        progress_callback=None,
        retry=3
    ):

        if self.engine == "ffmpeg":

            return await self.ffmpeg(
                url,
                output,
                duration,
                progress_callback,
                retry
            )

        if self.engine == "streamlink":

            return await self.streamlink(
                url,
                output,
                duration,
                progress_callback,
                retry
            )

        if self.engine == "yt-dlp":

            return await self.ytdlp(
                url,
                output,
                duration,
                progress_callback
            )

        if self.engine in (
            "n_m3u8dl_re",
            "n-m3u8dl-re"
        ):

            return await self.n_m3u8dl_re(
                url,
                output,
                duration
            )

        raise RecorderError(
            f"Unknown engine: {self.engine}"
        )

    async def ffmpeg(
        self,
        url,
        output,
        duration,
        progress_callback,
        retry
    ):

        cmd = [
            "ffmpeg",

            "-hide_banner",
            "-loglevel",
            "error",

            "-reconnect",
            "1",

            "-reconnect_streamed",
            "1",

            "-reconnect_at_eof",
            "1",

            "-reconnect_delay_max",
            "10",

            "-i",
            url,

            "-t",
            str(duration),

            "-map",
            "0",

            "-c",
            "copy",

            "-movflags",
            "+faststart",

            "-progress",
            "pipe:1",

            "-nostats",

            "-y",
            str(output)
        ]

        return await self._run(
            cmd,
            duration,
            progress_callback
        )

    async def streamlink(
        self,
        url,
        output,
        duration,
        progress_callback,
        retry
    ):

        streamlink = await asyncio.create_subprocess_exec(

            "streamlink",

            "--stdout",

            url,

            "best",

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE
        )

        ffmpeg = await asyncio.create_subprocess_exec(

            "ffmpeg",

            "-hide_banner",

            "-loglevel",
            "error",

            "-i",
            "pipe:0",

            "-t",
            str(duration),

            "-c",
            "copy",

            "-movflags",
            "+faststart",

            "-progress",
            "pipe:1",

            "-nostats",

            "-y",

            str(output),

            stdin=streamlink.stdout,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE
        )

        self.process = ffmpeg

        await self._progress_reader(
            ffmpeg,
            duration,
            progress_callback
        )

        rc = await ffmpeg.wait()

        try:
            streamlink.terminate()
        except Exception:
            pass

        await streamlink.wait()

        if rc != 0:

            raise RecorderError(
                "Streamlink/FFmpeg recording failed."
            )

        return output

    async def ytdlp(
        self,
        url,
        output,
        duration,
        progress_callback
    ):

        cmd = [
            "yt-dlp",

            "--no-part",

            "--no-mtime",

            "-o",
            str(output),

            url
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await self.process.communicate()

        if self.process.returncode != 0:

            raise RecorderError(
                stderr.decode(errors="ignore")[-2000:]
            )

        if progress_callback:

            await progress_callback(
                100,
                duration,
                duration
            )

        return output

    async def n_m3u8dl_re(
        self,
        url,
        output,
        duration
    ):

        cmd = [

            "N_m3u8DL-RE",

            url,

            "--save-name",
            Path(output).stem,

            "--save-dir",
            str(Path(output).parent),

            "--ffmpeg-binary-path",
            "ffmpeg",

            "--auto-select",

        ]

        self.process = await asyncio.create_subprocess_exec(

            *cmd,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await self.process.communicate()

        if self.process.returncode != 0:

            raise RecorderError(
                stderr.decode(errors="ignore")[-3000:]
            )

        return output

    async def _run(
        self,
        cmd,
        duration,
        progress_callback
    ):

        self.process = await asyncio.create_subprocess_exec(

            *cmd,

            stdout=asyncio.subprocess.PIPE,

            stderr=asyncio.subprocess.PIPE
        )

        await self._progress_reader(
            self.process,
            duration,
            progress_callback
        )

        stderr = await self.process.stderr.read()

        rc = await self.process.wait()

        if rc != 0:

            raise RecorderError(
                stderr.decode(errors="ignore")[-3000:]
            )

        return True

    async def _progress_reader(
        self,
        process,
        duration,
        callback
    ):

        last_update = 0

        while True:

            line = await process.stdout.readline()

            if not line:
                break

            text = line.decode(
                errors="ignore"
            ).strip()

            if text.startswith(
                "out_time_us="
            ):

                try:

                    us = int(
                        text.split("=")[1]
                    )

                    elapsed = us / 1_000_000

                    percent = (
                        elapsed /
                        duration
                    ) * 100

                    percent = min(
                        100,
                        percent
                    )

                    now = asyncio.get_event_loop().time()

                    if (
                        callback and
                        now - last_update >= 2
                    ):

                        await callback(
                            percent,
                            elapsed,
                            duration
                        )

                        last_update = now

                except Exception:
                    pass

    async def cancel(self):

        if not self.process:
            return

        try:

            self.process.send_signal(
                signal.SIGINT
            )

        except Exception:

            try:
                self.process.kill()
            except Exception:
                pass