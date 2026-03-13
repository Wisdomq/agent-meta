import sys

blueprint = {
    "Foundation": ["Excavation", "Concrete Pouring"],
    "Framing": ["Wood Framing", "Steel Framing"],
    "Plumbing": ["Pipe Laying", "Fixture Installation"],
    "Electrical": ["Wiring", "Socket Installation"],
    "Insulation": ["Wall Insulation", "Roof Insulation"],
    "Drywall": ["Drywall Hanging", "Taping and Texturing"],
    "Painting": ["Interior Painting", "Exterior Painting"],
    "Flooring": ["Hardwood Flooring", "Tile Flooring"],
    "Roofing": ["Shingle Installation", "Flashing Installation"],
}

for category, items in blueprint.items():
    print(f"{category}:")
    for item in items:
        print(f"  - {item}")