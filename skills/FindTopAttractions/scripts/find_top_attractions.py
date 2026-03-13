import sys

destination = sys.argv[1]

categories = {
    "Must-See Landmarks": ["The Grand Museum", "Historic Old Town", f"{destination} National Monument"],
    "Natural Wonders": ["National Park", "River Valley", f"{destination} Coastal Reserve"],
    "Local Experiences": ["Street Food Market", "Cultural Festival", f"Traditional {destination} Village"]
}

for category, items in categories.items():
    print(f"\n{category}:")
    for item in items:
        print(f"  - {item}")