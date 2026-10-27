# 1.3 Subtract Whole Numbers

## Learning Objectives

- Read and write subtraction.
- Subtract with base-10 blocks, trading a ten for ten ones.
- Subtract whole numbers column by column, borrowing, and check by adding.
- Translate word phrases such as *the difference of* and *less than* into subtraction.
- Subtract whole numbers to solve problems.

## Be Prepared

**1.** Add $386 + 457$.

```answer
Number(843)
```

**2.** Translate and simplify: *fifteen more than twenty-eight*.

```answer
Number(43)
```

If you missed either one, go back to [1.2 Add Whole Numbers](lesson:math/prealgebra-2e/1.2). For place value, see [1.1 Introduction to Whole Numbers](lesson:math/prealgebra-2e/1.1).

## Subtraction Notation

The symbol $-$ means **subtraction**. In $9 - 4 = 5$ the result, $5$, is the **difference**. We read it "nine minus four equals five" or "the difference of nine and four is five".

Subtraction undoes addition: $9 - 4 = 5$ because $5 + 4 = 9$. So every subtraction can be **checked by adding** the difference and the number taken away.

**Example 1.** Find $14 - 6$ by thinking of an addition.

*Solution.* What added to $6$ makes $14$? $8 + 6 = 14$, so $14 - 6 = 8$.

**Try it.** Since $27 + 15 = 42$, what is $42 - 15$?

```answer
Number(27)
```

## Modelling Subtraction

With base-10 blocks, put out the larger number and take the smaller away. When a column has too few cubes, trade one rod for ten cubes first.

**Example 2.** Find $43 - 26$ with blocks.

*Solution.* $43$ is 4 rods and 3 cubes. We can't take 6 cubes from 3, so trade a rod: 3 rods and 13 cubes. Take away 2 rods and 6 cubes: 1 rod and 7 cubes are left, so $43 - 26 = 17$.

## Subtracting Whole Numbers

Write the larger number on top with the places lined up, and subtract column by column from the ones. When the top digit is smaller than the one under it, **borrow**: take one from the next column to the left, which is worth ten in this column.

**Example 3.** Subtract $6{,}032 - 2{,}748$ and check.

*Solution.*

- Ones: $2 - 8$ won't go. The tens has $3$: borrow, leaving $2$ tens, and the ones become $12$. $12 - 8 = 4$.
- Tens: $2 - 4$ won't go. The hundreds has $0$, so borrow from the thousands first: $5$ thousands, $10$ hundreds; then $9$ hundreds and $12$ tens. $12 - 4 = 8$.
- Hundreds: $9 - 7 = 2$.
- Thousands: $5 - 2 = 3$.

So $6{,}032 - 2{,}748 = 3{,}284$. Check: $3{,}284 + 2{,}748 = 6{,}032$.

**Try it.** Subtract $832 - 467$.

```answer
Number(365)
```

**Try it.** Subtract $5{,}003 - 1{,}758$.

```answer
Number(3245)
```

## Translating Words into Subtraction

| Words | Subtraction |
|---|---|
| the difference of $a$ and $b$ | $a - b$ |
| $a$ minus $b$ | $a - b$ |
| $a$ decreased by $b$ | $a - b$ |
| $b$ less than $a$ | $a - b$ |
| $b$ subtracted from $a$ | $a - b$ |

Watch the order: *$5$ less than $12$* is $12 - 5$, not $5 - 12$.

**Example 4.** Translate and simplify: *eighteen subtracted from fifty*.

*Solution.* $50 - 18 = 32$.

**Try it.** Translate and simplify: *36 less than 91*.

```answer
Number(55)
```

## Subtracting to Solve Problems

*How many are left*, *how many more* and *how much change* are subtractions.

**Example 5.** A stadium holds $45{,}800$ people and $38{,}975$ tickets are sold. How many seats are left?

*Solution.* $45{,}800 - 38{,}975 = 6{,}825$: there are $6{,}825$ seats left.

**Try it.** In the morning it was $64$ degrees; by night it was $47$ degrees. By how many degrees did it fall?

```answer
Number(17)
```

## Key Concepts

- In $a - b$, the result is the **difference**; subtraction undoes addition.
- Subtract column by column from the ones, **borrowing** one from the next column (worth ten here) when the top digit is too small. Across a zero, borrow from further left first.
- Check a subtraction by adding the difference to the number taken away.
- *Difference of*, *minus*, *decreased by*, *less than* and *subtracted from* mean subtraction; with *less than* and *subtracted from* the order turns round.

## Key Terms

**difference**: the result of subtracting. **borrowing** (regrouping): trading one of a place for ten of the place to its right.

## Lab

The lab draws subtraction on a number line. **Run the lab** (F5) and type two numbers: it hops back from the first number by the hundreds, the tens and the ones of the second and lands on the difference. Tick **Count up** to see the other way of finding a difference: hop from the smaller number up to the larger one, to the next ten, the next hundred and so on, and add up the hops.

Then change the program:

1. Find `hops_back` in `Form1`. Make it hop by thousands too.
2. The difference is the distance between the two numbers. Add a label that says so, and check it with an addition: difference plus the smaller number.

---

Adapted from "1.3 Subtract Whole Numbers" in *Prealgebra 2e* by Lynn Marecek, MaryAnne Anthony-Smith and Andrea Honeycutt Mathis (OpenStax), <https://openstax.org/books/prealgebra-2e/pages/1-3-subtract-whole-numbers>, licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
