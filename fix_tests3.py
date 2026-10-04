import os

text = open("tests/test_diff.py").read()
text = text.replace('diff_res = subprocess.run', 'print("HISTORY:", res.stdout)\n    diff_res = subprocess.run')
open("tests/test_diff.py", "w").write(text)

text2 = open("tests/test_timeline.py").read()
text2 = text2.replace('res_proj = subprocess.run', 'print("PROJECT TIMELINE STDOUT:", res_proj.stdout)\n    res_proj = subprocess.run')
open("tests/test_timeline.py", "w").write(text2)
