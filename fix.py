lines = open('recovery.py').read().splitlines()
start_idx = 0
for i in range(len(lines)):
    if lines[i] == 'import difflib':
        start_idx = i
        break

if start_idx > 0:
    lines = lines[:start_idx]
    
with open('recovery.py', 'w') as f:
    f.write('\n'.join(lines) + '\n')
