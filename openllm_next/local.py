import asyncio
import httpx

import questionary

from openllm_next.common import (
    BentoInfo,
    run_command,
    async_run_command,
    stream_command_output,
)
from openllm_next.venv import ensure_venv


def _get_serve_cmd(bento: BentoInfo):
    cmd = ["bentoml", "serve", bento.tag]
    env = {
        "BENTOML_HOME": f"{bento.repo.path}/bentoml",
    }
    return cmd, env, None


def serve(bento: BentoInfo):
    venv = ensure_venv(bento)
    cmd, env, cwd = _get_serve_cmd(bento)
    run_command(cmd, env=env, cwd=cwd, venv=venv)


async def _run_model(bento: BentoInfo, timeout: int = 600):
    venv = ensure_venv(bento)
    cmd, env, cwd = _get_serve_cmd(bento)
    server_proc = await async_run_command(
        cmd,
        env=env,
        cwd=cwd,
        venv=venv,
        silent=False,
    )
    stdout_streamer = asyncio.create_task(
        stream_command_output(server_proc.stdout, style="gray")
    )
    stderr_streamer = asyncio.create_task(
        stream_command_output(server_proc.stderr, style="#BD2D0F")
    )

    import bentoml

    try:
        questionary.print("Model loading...", style="green")
        for _ in range(timeout):
            try:
                resp = httpx.get("http://localhost:3000/readyz", timeout=3)
                if resp.status_code == 200:
                    break
            except httpx.RequestError:
                await asyncio.sleep(0)
        else:
            questionary.print("Model failed to load", style="red")
            server_proc.terminate()
            return

        stdout_streamer.cancel()
        stderr_streamer.cancel()

        questionary.print("Model is ready", style="green")
        messages = []
        client = bentoml.AsyncHTTPClient("http://localhost:3000", timeout=timeout)
        while True:
            try:
                message = input("user: ")
                messages.append(dict(role="user", content=message))
                print("assistant: ", end="")
                assistant_message = ""
                async for text in client.chat(messages=messages):  # type: ignore
                    assistant_message += text
                    print(text, end="")
                messages.append(dict(role="assistant", content=assistant_message))
                print()

            except KeyboardInterrupt:
                break
    except (asyncio.CancelledError, httpx.RequestError):
        pass
    finally:
        questionary.print("\nStopping model server...", style="green")
        if server_proc.returncode is None:
            server_proc.terminate()
        await server_proc.wait()
        questionary.print("Stopped model server", style="green")


def run(bento: BentoInfo):
    asyncio.run(_run_model(bento))
