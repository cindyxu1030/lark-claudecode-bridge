import asyncio
import os
import sys

import pytest

os.environ.setdefault("FEISHU_APP_ID", "test_app_id")
os.environ.setdefault("FEISHU_APP_SECRET", "test_app_secret")
os.environ.setdefault("CODEX_HOME", "/tmp/test-codex-home")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codex_runner import run_codex


class FakeStdin:
    def __init__(self):
        self.buffer = b""
        self.closed = False

    def write(self, data: bytes):
        self.buffer += data

    async def drain(self):
        return None

    def close(self):
        self.closed = True


class FakeStdout:
    def __init__(self, lines: list[bytes]):
        self._lines = list(lines)
        self._index = 0

    async def readline(self):
        if self._index >= len(self._lines):
            return b""
        line = self._lines[self._index]
        self._index += 1
        return line


class FakeStderr:
    def __init__(self, data: bytes):
        self._data = data

    async def read(self):
        return self._data


class FakeProc:
    def __init__(self, stdout_lines: list[bytes], stderr: bytes = b"", returncode: int = 0):
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(stdout_lines)
        self.stderr = FakeStderr(stderr)
        self.returncode = returncode

    async def wait(self):
        return self.returncode

    def kill(self):
        pass


def test_run_codex_reads_thread_and_final_agent_message(monkeypatch):
    proc = FakeProc([
        b'{"type":"thread.started","thread_id":"019abc"}\n',
        b'{"type":"turn.started"}\n',
        b'{"type":"item.completed","item":{"type":"agent_message","text":"Hello from Codex"}}\n',
        b'{"type":"turn.completed"}\n',
    ])

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    text, session_id, used_fallback = asyncio.run(run_codex("hi"))

    assert text == "Hello from Codex"
    assert session_id == "019abc"
    assert used_fallback is False
    assert proc.stdin.buffer.endswith(b"hi\n")
    assert proc.stdin.closed is True


def test_run_codex_resumes_existing_thread(monkeypatch):
    proc = FakeProc([
        b'{"type":"item.completed","item":{"type":"agent_message","text":"resumed"}}\n',
    ])
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    text, session_id, used_fallback = asyncio.run(run_codex("hi", session_id="019old"))

    assert text == "resumed"
    assert session_id == "019old"
    assert used_fallback is False
    assert captured["args"][1:4] == ("exec", "resume", "--json")


def test_run_codex_raises_on_nonzero_without_output(monkeypatch):
    proc = FakeProc([], stderr=b"fatal", returncode=1)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(RuntimeError, match="fatal"):
        asyncio.run(run_codex("hi"))

