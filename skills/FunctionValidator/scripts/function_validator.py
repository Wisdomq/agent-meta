import sys
import math

def test_function1():
    def add(a, b):
        return a + b

    for i in range(-100, 100):
        for j in range(-100, 100):
            result = add(i, j)
            expected_result = i + j
            assert result == expected_result, f"Function add failed with inputs {i}, {j}"

def test_function2():
    def multiply(a, b):
        return a * b

    for i in range(-100, 100):
        for j in range(-100, 100):
            result = multiply(i, j)
            expected_result = i * j
            assert result == expected_result, f"Function multiply failed with inputs {i}, {j}"

def test_function3():
    def find_max(numbers):
        max_number = numbers[0]
        for number in numbers:
            if number > max_number:
                max_number = number
        return max_number

    numbers = [-10, -5, 0, 5, 10]
    result = find_max(numbers)
    expected_result = max(numbers)
    assert result == expected_result, f"Function find_max failed with inputs {numbers}"

def test_function4():
    def is_prime(number):
        if number < 2:
            return False
        for i in range(2, int(math.sqrt(number)) + 1):
            if number % i == 0:
                return False
        return True

    numbers = [2, 3, 4, 5, 6]
    primes = []
    for number in numbers:
        if is_prime(number):
            primes.append(number)
    result = len(primes)
    expected_result = len([x for x in numbers if x <= 3 and is_prime(x)])
    assert result == expected_result, f"Function is_prime failed with inputs {numbers}"

if __name__ == "__main__":
    test_function1()
    print("Function add tests passed.")
    test_function2()
    print("Function multiply tests passed.")
    test_function3()
    print("Function find_max tests passed.")
    test_function4()
    print("Function is_prime tests passed.")