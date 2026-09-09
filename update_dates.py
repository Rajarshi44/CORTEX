import glob
import os

for f in glob.glob('demo-case-data/*.csv'):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    content = content.replace('2025-', '2026-').replace('2024-', '2025-')
    with open(f, 'w', encoding='utf-8') as file:
        file.write(content)
print("Updated all CSV dates!")
