import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.loadenv import load_env  # noqa: E402

p = Path("tests/_env_test.txt")
p.parent.mkdir(exist_ok=True)
p.write_text(
    "# 注释行应被忽略\n"
    "\n"
    "HARNESS_BACKEND=openai\n"
    'HARNESS_API_KEY = "sk-test123456789"\n'
    "HARNESS_BASE_URL=https://api.deepseek.com\n",
    encoding="utf-8",
)
os.environ.pop("HARNESS_BACKEND", None)
got = load_env(p)
print("parsed :", got)
print("env    :", os.environ.get("HARNESS_BACKEND"),
      "|", os.environ.get("HARNESS_API_KEY"),
      "|", os.environ.get("HARNESS_BASE_URL"))
p.unlink()
