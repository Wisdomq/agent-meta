import sys
import math

number = int(sys.argv[1])

prime_sequence = []
fibonacci_sequence = [0, 1]
even_odd_sequence = [0]
square_sequence = []
cube_sequence = []

for i in range(2, number + 1):
    if all(i % j != 0 for j in prime_sequence):
        prime_sequence.append(i)

    fibonacci_sequence.append(fibonacci_sequence[-1] + fibonacci_sequence[-2])

    if i % 2 == 0:
        even_odd_sequence.append(i)
    else:
        even_odd_sequence.append("Odd")

    square = i ** 2
    if square not in square_sequence:
        square_sequence.append(square)

    cube = i ** 3
    if cube not in cube_sequence:
        cube_sequence.append(cube)

print("Prime Sequence:")
for item in prime_sequence:
    print(f"  - {item}")

print("\nFibonacci Sequence:")
for item in fibonacci_sequence:
    print(f"  - {item}")

print("\nEven/Odd Sequence:")
for item in even_odd_sequence:
    print(f"  - {item}")

print("\nSquare Sequence:")
for item in square_sequence:
    print(f"  - {math.sqrt(item)}")

print("\nCube Sequence:")
for item in cube_sequence:
    print(f"  - {math.cbrt(item)}")