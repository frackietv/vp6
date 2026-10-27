# Chapter 1 Practice Test

Take this test as you would a real one: without the lessons open, without a calculator, and in about half an hour. Answer every question before checking any of them; then check, and for each one you missed read again the lesson named after it. The Exercises tab gives a new test, with new numbers, each time you press **New Numbers**.

## The Test

**1.** Write *six million, three hundred four thousand, ninety* with digits. (1.1)

```answer
Number(6304090)
```

**2.** Which digit is in the ten thousands place of $3{,}852{,}716$? (1.1)

```answer
Number(5)
```

**3.** Round $596{,}482$ to the nearest ten thousand. (1.1)

```answer
Number(600000)
```

**4.** Add $47{,}386 + 9{,}857$. (1.2)

```answer
Number(57243)
```

**5.** Translate and simplify: *the sum of 245 and 378*. (1.2)

```answer
Number(623)
```

**6.** Subtract $40{,}015 - 18{,}679$. (1.3)

```answer
Number(21336)
```

**7.** Translate and simplify: *46 subtracted from 100*. (1.3)

```answer
Number(54)
```

**8.** Multiply $389 \times 47$. (1.4)

```answer
Number(18283)
```

**9.** Multiply $7{,}000 \times 30$. (1.4)

```answer
Number(210000)
```

**10.** Divide $9{,}744 \div 24$. (1.5)

```answer
Number(406)
```

**11.** What is $15 \div 0$? (A) $0$ (B) $15$ (C) $1$ (D) undefined (1.5)

```answer
Choice("D", ["0", "15", "1", "undefined"])
```

**12.** A school orders $36$ boxes of pencils with $48$ pencils in each, and shares them equally among $24$ classes. How many pencils does each class get? (1.4, 1.5)

```answer
Number(72)
```

**13.** A garden is $23$ feet long and $15$ feet wide. How many feet of fence go round it, and what is its area? Give (perimeter, area). (1.2, 1.4)

```answer
Pair((76, 345), names=("perimeter", "area"))
```

## After the Test

Missed a question? Each one names its section: [1.1](lesson:math/prealgebra-2e/1.1), [1.2](lesson:math/prealgebra-2e/1.2), [1.3](lesson:math/prealgebra-2e/1.3), [1.4](lesson:math/prealgebra-2e/1.4), [1.5](lesson:math/prealgebra-2e/1.5). The [chapter review](lesson:math/prealgebra-2e/1-review) has more of each kind.

## Lab

The lab is a whole-number calculator to check your work after the test (not during it!). **Run the lab** (F5), type two numbers and press an operation: division gives a quotient and a remainder, and dividing by zero says why it can't.

Then change the program:

1. Find `calculate` in `Form1`. Add a **Round** button that rounds the first number to the place chosen in a combo box (tens, hundreds, thousands...).
2. Add a **Check** line under the result: for subtraction the addition that checks it, for division quotient × divisor + remainder.
3. Make the calculator name its answer in words, using `name_of` from the lab of [1.1](lesson:math/prealgebra-2e/1.1).

---

Adapted from "Chapter 1: Practice Test" in *Prealgebra 2e* by Lynn Marecek, MaryAnne Anthony-Smith and Andrea Honeycutt Mathis (OpenStax), <https://openstax.org/books/prealgebra-2e/pages/1-practice-test>, licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
