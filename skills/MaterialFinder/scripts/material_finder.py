import os

PROJECT = "Python Project"
MATERIALS = {
    "Programming": ["Python", "IDE (Integrated Development Environment)", "Laptop"],
    "Hardware": ["Circuit Board", "Resistors", "Capacitors"],
    "Software": ["Text Editor", "Version Control System", "Compilation Tool"]
}

print(f"Project: {PROJECT}")
print("Material Categories:")
for category, items in MATERIALS.items():
    print(f"\n{category}:")
    for item in items:
        print(f"  - {item}")