import sys

number = int(sys.argv[1])

addition = number + 10
subtraction = number - 10
multiplication = number * 10
division = number / 10 if number != 0 else "Error: Division by zero"

print(f"Addition: {addition}")
print(f"Subtraction: {subtraction}")
print(f"Multiplication: {multiplication}")
print(f"Division: {division}")