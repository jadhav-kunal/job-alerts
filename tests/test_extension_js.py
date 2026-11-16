import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_extension_answer_matching():
    r = subprocess.run(["node", str(Path(__file__).with_name("answer_matching.test.js"))], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "cases passed" in r.stdout


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_extension_length_limits():
    r = subprocess.run(["node", str(Path(__file__).with_name("length_limits.test.js"))], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "cases passed" in r.stdout
