import random
import string

EXERCISES = {
    "push-ups": {"sets": 3, "reps": 10},
    "squats": {"sets": 4, "reps": 12},
    "lunges": {"sets": 3, "reps": 8},
    "pull-ups": {"sets": 2, "reps": 6},
    "dips": {"sets": 3, "reps": 10},
    "plank": {"sets": 2, "time": 60},
    "burpees": {"sets": 2, "reps": 8},
}

def generate_workout():
    exercises = random.sample(list(EXERCISES.keys()), len(EXERCISES))

    workout = {}
    for exercise in exercises:
        workout[exercise] = EXERCISES[exercise].copy()

    return workout

def format_workout(workout):
    output = ""
    for exercise, data in workout.items():
        if "time" in data:
            output += f"{data['sets']} sets of {exercise}: Hold the plank for {data['time']} seconds\n"
        else:
            output += f"{data['sets']} sets of {exercise}: {data['reps']} reps\n"
    return output

def main():
    workout = generate_workout()
    print(format_workout(workout))

if __name__ == "__main__":
    main()