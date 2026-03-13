import calendar
import random

MEALS = [
    "Spaghetti Bolognese",
    "Chicken Curry",
    "Vegetable Stir Fry",
    "Grilled Salmon",
    "Pizza Margherita",
    "Tacos",
    "Lasagna",
    "Fried Rice",
    "Meatballs with Spaghetti",
    "Chicken Caesar Salad",
    "Beef Stew",
    "Sushi Rolls"
]

def get_days():
    return [calendar.day_name[x] for x in range(2, calendar.weekday, 7)]

def get_meals():
    days = get_days()
    meal_schedule = {}

    for day in days:
        meal_schedule[day] = random.choice(MEALS)

    return meal_schedule

if __name__ == "__main__":
    print("Weekly Meal Schedule:")
    meal_schedule = get_meals()
    for day, meal in meal_schedule.items():
        print(f"{day}: {meal}")