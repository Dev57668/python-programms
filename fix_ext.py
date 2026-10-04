import os

for f in ["tests/test_diff.py", "tests/test_timeline.py"]:
    text = open(f).read()
    text = text.replace(".txt", ".py")
    text = text.replace('print("HISTORY:", res.stdout)', '')
    text = text.replace('print("PROJECT TIMELINE STDOUT:", res_proj.stdout)', '')
    open(f, "w").write(text)
