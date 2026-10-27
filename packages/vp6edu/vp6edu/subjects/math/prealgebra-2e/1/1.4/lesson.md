# 1.4 Multiply Whole Numbers

## Learning Objectives

- Read and write multiplication.
- Show a multiplication as an array.
- Multiply whole numbers, using the properties of zero and one and partial products.
- Translate word phrases such as *the product of* and *twice* into multiplication.
- Multiply whole numbers to solve problems, areas included.

## Be Prepared

**1.** Add $46 + 46 + 46$.

```answer
Number(138)
```

**2.** Subtract $1{,}000 - 386$.

```answer
Number(614)
```

If you missed the first, go back to [1.2 Add Whole Numbers](lesson:math/prealgebra-2e/1.2); the second, [1.3 Subtract Whole Numbers](lesson:math/prealgebra-2e/1.3).

## Multiplication Notation

Multiplication is repeated addition: $4 \times 3$ means four threes, $3 + 3 + 3 + 3 = 12$. The numbers multiplied are **factors** and the result is the **product**. Besides $\times$, multiplication is written with a dot, $4 \cdot 3$, or with parentheses, $4(3)$ or $(4)(3)$.

| Operation | Notation | Read as | Result |
|---|---|---|---|
| multiplication | $a \times b$, $a \cdot b$, $a(b)$ | $a$ times $b$ | the product of $a$ and $b$ |

## Modelling Multiplication

An **array** is a rectangle of objects in rows and columns. $3$ rows of $5$ is $3 \times 5 = 15$ objects. Turn the array on its side and it is $5$ rows of $3$: the same $15$. That is the **commutative property**: $a \cdot b = b \cdot a$.

**Example 1.** A theatre has $14$ rows of $22$ seats. Write the number of seats as a multiplication.

*Solution.* $14 \times 22$ (or $22 \times 14$): $308$ seats.

## Multiplying Whole Numbers

Two numbers make multiplying easy:

- **Multiplication by zero:** $a \cdot 0 = 0$. No groups of anything is nothing.
- **The identity property:** $a \cdot 1 = a$. One group of $a$ is $a$.

Multiplying by $10$, $100$ or $1{,}000$ puts one, two or three zeros on the end: $47 \times 100 = 4{,}700$. With zeros at the ends of factors, multiply the rest and then put back all the zeros: $300 \times 40 = 12{,}000$.

To multiply by a number of several digits, multiply by each of its digits in turn (a **partial product**), shifting each one place left, then add the partial products.

**Example 2.** Multiply $346 \times 27$.

*Solution.*

- $346 \times 7 = 2{,}422$.
- $346 \times 20 = 6{,}920$.
- Add: $2{,}422 + 6{,}920 = 9{,}342$.

So $346 \times 27 = 9{,}342$.

**Try it.** Multiply $58 \times 34$.

```answer
Number(1972)
```

**Try it.** Multiply $600 \times 50$.

```answer
Number(30000)
```

## Translating Words into Multiplication

| Words | Multiplication |
|---|---|
| the product of $a$ and $b$ | $a \cdot b$ |
| $a$ times $b$ | $a \cdot b$ |
| twice $a$ | $2 \cdot a$ |
| triple $a$ | $3 \cdot a$ |

**Example 3.** Translate and simplify: *twice 125*.

*Solution.* $2 \cdot 125 = 250$.

**Try it.** Translate and simplify: *the product of 16 and 9*.

```answer
Number(144)
```

## Multiplying to Solve Problems

*Each*, *per* and *rows of* often mean multiplication.

**Example 4.** A box holds $24$ cans. How many cans are in $15$ boxes?

*Solution.* $15 \times 24 = 360$ cans.

The **area** of a rectangle is the number of unit squares that cover it: its length times its width, in square units.

**Example 5.** A room is $16$ feet long and $12$ feet wide. What is its area?

*Solution.* $16 \times 12 = 192$ square feet.

**Try it.** A rectangular patio is $9$ metres by $14$ metres. What is its area, in square metres?

```answer
Number(126)
```

## Key Concepts

- In $a \cdot b$, $a$ and $b$ are **factors** and the result is the **product**.
- $a \cdot 0 = 0$; $a \cdot 1 = a$ (the **identity property**); $a \cdot b = b \cdot a$ (the **commutative property**).
- Multiply by a many-digit number one digit at a time (partial products), then add.
- *Product of*, *times*, *twice* and *triple* mean multiplication.
- The **area** of a rectangle is its length times its width.

## Key Terms

**factor**: a number being multiplied. **product**: the result of multiplying. **area**: the number of unit squares covering a figure.

## Lab

The lab draws a multiplication as an array of squares, which is also the area of a rectangle. **Run the lab** (F5) and drag the sliders for the rows and the columns. **Turn** swaps them: the product doesn't change. Tick **Split by place** to cut the columns into tens and ones: the two parts are the partial products, and they add up to the whole.

Then change the program:

1. Find `cmdTurn_Click` in `Form1` and make the lab say "commutative property" when you turn the array.
2. Split the rows by place too, so that $13 \times 24$ shows four parts: $10 \times 20$, $10 \times 4$, $3 \times 20$ and $3 \times 4$.

---

Adapted from "1.4 Multiply Whole Numbers" in *Prealgebra 2e* by Lynn Marecek, MaryAnne Anthony-Smith and Andrea Honeycutt Mathis (OpenStax), <https://openstax.org/books/prealgebra-2e/pages/1-4-multiply-whole-numbers>, licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
