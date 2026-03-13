import sys

if len(sys.argv) != 2:
    print("Usage: python count_lines.py <filename>")
    exit()

file_name = sys.argv[1]

with open(file_name, 'r') as file:
    lines = file.readlines()

print(f"Number of lines in {file_name}: {len(lines)}")