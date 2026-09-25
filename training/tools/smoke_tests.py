"""Run simple test functions when pytest installation is unavailable.

This supports only the tmp_path fixture used in this project's tests.
CI uses pytest directly.
"""
import inspect
from pathlib import Path
import runpy
import uuid

passed = 0
for path in sorted(Path("tests").glob("test_*.py")):
    namespace = runpy.run_path(str(path))
    for name, function in namespace.items():
        if name.startswith("test_") and callable(function):
            directory = Path("work") / "smoke" / uuid.uuid4().hex
            directory.mkdir(parents=True)
            kwargs = {key: directory for key in inspect.signature(function).parameters}
            function(**kwargs)
            passed += 1
            print(f"PASS {path.name}::{name}")
print(f"{passed} tests passed (direct runner, not pytest)")
