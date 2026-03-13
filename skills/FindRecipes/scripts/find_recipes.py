import json
import random
from collections import namedtuple

Meal = namedtuple('Meal', 'name, ingredients')

RECIPES = {
    'spaghetti': ['tomato sauce', 'spaghetti', 'garlic', 'onion', 'olive oil'],
    'pizza': ['pizza dough', 'tomato sauce', 'mozzarella cheese', 'pepperoni'],
    'burger': ['ground beef', 'bread buns', 'lettuce', 'tomato', 'pickles'],
}

MEALS = [Meal('spaghetti', RECIPES['spaghetti']), Meal('pizza', RECIPES['pizza']), Meal('burger', RECIPES['burger'])]

def random_meal():
    return random.choice(MEALS)

def main():
    meal = random_meal()
    print(f'Recipe for {meal.name}')
    print('Ingredients:')
    for ingredient in meal.ingredients:
        print(f'\t{ingredient}')

if __name__ == '__main__':
    main()