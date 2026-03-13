import sys

SUBJECT = sys.argv[1].lower()

HOUSE_STYLES = {
    "cottage": ["Cozy Cottage", "Victorian Cottage", "Modern Cottage"],
    "contemporary": ["Minimalist House", "Sleek Modern Home", "Glass House"],
    "traditional": ["Colonial House", "Tudor House", "Craftsman Bungalow"],
}

for style, designs in HOUSE_STYLES.items():
    print(f"{style.capitalize()} Blueprints:")
    for design in designs:
        print(f"  - {SUBJECT} {design}")