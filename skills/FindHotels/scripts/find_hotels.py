import sys

destination = sys.argv[1]

hotel_categories = {
    "Top Rated Hotels": ["The Serena Lake Victoria Hotel Entebbe", "Protea Hotel by Marriott Entebbe"],
    "Budget Friendly Hotels": ["Entebbe Airport Guesthouse", "Lake Victoria View Guest House"],
    "Luxury Hotels": ["Chateau Lake Victoria", "Protea Hotel by Marriott Entebbe"]
}

for category, hotels in hotel_categories.items():
    print(f"{category}:")
    for hotel in hotels:
        print(f"  - {hotel.replace('Entebbe', destination)}")