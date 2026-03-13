import random
import string

def generate_workout():
    exercises = {
        "cardio": ["Jogging", "Swimming", "Cycling"],
        "strength": ["Push-ups", "Squats", "Lunges", "Pull-ups"]
    }

    workout = {}
    for category in exercises:
        exercise = random.choice(exercises[category])
        sets = random.randint(3, 5)
        reps = random.randint(10, 20)
        workout[category] = {
            "exercise": exercise,
            "sets": sets,
            "reps": reps
        }
    return workout

def print_workout(workout):
    for category, details in workout.items():
        print(f"Category: {category}")
        print(f"Exercise: {details['exercise']}")
        print(f"Sets: {details['sets']}")
        print(f"Reps: {details['reps']}")
        print("-" * 30)

if __name__ == "__main__":
    workout = generate_workout()
    print_workout(workout)