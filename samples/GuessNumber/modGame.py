from vp6 import *
import random


def Main():
    print("I'm thinking of a number between 1 and 100.")
    secret = random.randint(1, 100)
    tries = 0
    while True:
        answer = input("Your guess: ")
        if not answer.strip().isdigit():
            print("Please type a whole number.")
            continue
        guess, tries = int(answer), tries + 1
        if guess < secret:
            print("Higher!")
        elif guess > secret:
            print("Lower!")
        else:
            print(f"Correct! You needed {tries} tries.")
            return 0


if __name__ == "__main__":
    Main()
