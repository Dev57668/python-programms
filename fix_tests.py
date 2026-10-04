import os
import pathlib

root = pathlib.Path(__file__).parent.resolve()
main_script = str(root / "main.py")

for f in ["tests/test_diff.py", "tests/test_timeline.py"]:
    text = open(f).read()
    text = text.replace("add_snapshot", "create_snapshot")
    text = text.replace('["python3", "../../main.py"', f'["python3", "{main_script}"')
    open(f, "w").write(text)

