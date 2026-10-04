import os

for f in ["tests/test_diff.py"]:
    text = open(f).read()
    text = text.replace('subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "watch", str(project_dir)], cwd=str(project_dir), timeout=2)',
                        'try:\n        subprocess.run(["python3", "/Users/bhaveshlakhmani/Documents/antigravity/pyhtonproject/python-programms/main.py", "watch", str(project_dir)], cwd=str(project_dir), timeout=2)\n    except subprocess.TimeoutExpired:\n        pass')
    open(f, "w").write(text)

text2 = open("tests/test_timeline.py").read()
text2 = text2.replace("handle_deleted", "handle_deletion")
open("tests/test_timeline.py", "w").write(text2)
