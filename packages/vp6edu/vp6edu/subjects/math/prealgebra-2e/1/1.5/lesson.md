# 1.5 Divide Whole Numbers

## Learning Objectives

- Read and write division.
- Show a division as sharing into equal groups.
- Divide whole numbers by long division, with remainders, and check by multiplying.
- Know what dividing by one, by itself and by zero gives.
- Translate word phrases such as *the quotient of* into division.
- Divide whole numbers to solve problems.

## Be Prepared

**1.** Multiply $48 \times 7$.

```answer
Number(336)
```

**2.** Subtract $91 - 84$.

```answer
Number(7)
```

If you missed the first, go back to [1.4 Multiply Whole Numbers](lesson:math/prealgebra-2e/1.4); the second, [1.3 Subtract Whole Numbers](lesson:math/prealgebra-2e/1.3).

## Division Notation

Division splits a number into equal groups. In $12 \div 3 = 4$, $12$ is the **dividend**, $3$ the **divisor** and $4$ the **quotient**. Division is also written with a fraction bar, $\frac{12}{3}$, or with a long-division bracket.

Division undoes multiplication: $12 \div 3 = 4$ because $4 \cdot 3 = 12$.

**Example 1.** Find $56 \div 8$ by thinking of a multiplication.

*Solution.* What times $8$ is $56$? $7 \cdot 8 = 56$, so $56 \div 8 = 7$.

**Try it.** Since $9 \cdot 13 = 117$, what is $117 \div 9$?

```answer
Number(13)
```

## Modelling Division

Sharing $20$ counters among $4$ people, one at a time round the circle, gives each $5$: $20 \div 4 = 5$. Sharing $23$ among $4$ gives each $5$ with $3$ left over: the **remainder**. We write $23 \div 4 = 5$ R $3$.

## Dividing Whole Numbers

Some divisions you know at once:

- $a \div 1 = a$: one group holds everything.
- $a \div a = 1$ (for $a$ not zero): $a$ shared among $a$ is one each.
- $0 \div a = 0$ (for $a$ not zero): nothing shared is nothing each.
- $a \div 0$ is **undefined**: no number times $0$ gives $a$.

For larger numbers, **long division** works from the left, one digit of the dividend at a time:

1. Divide: how many times does the divisor go into the part of the dividend you are looking at? Write that digit in the quotient.
2. Multiply that digit by the divisor, and subtract.
3. Bring down the next digit and repeat.

Check: quotient times divisor, plus the remainder, gives the dividend.

**Example 2.** Divide $2{,}596 \div 4$.

*Solution.*

- $4$ doesn't go into $2$, so look at $25$: $6$ times ($24$), leaving $1$.
- Bring down $9$: $19$. $4$ goes $4$ times ($16$), leaving $3$.
- Bring down $6$: $36$. $4$ goes $9$ times exactly.

So $2{,}596 \div 4 = 649$. Check: $649 \cdot 4 = 2{,}596$.

**Try it.** Divide $1{,}834 \div 7$.

```answer
Number(262)
```

**Example 3.** Divide $963 \div 28$.

*Solution.* $28$ goes into $96$ $3$ times ($84$), leaving $12$. Bring down $3$: $123$. $28$ goes $4$ times ($112$), leaving $11$. So $963 \div 28 = 34$ R $11$. Check: $34 \cdot 28 + 11 = 952 + 11 = 963$.

**Try it.** Divide $500 \div 12$. Give the quotient and the remainder as a pair, (quotient, remainder).

```answer
Pair((41, 8), names=("quotient", "remainder"))
```

## Translating Words into Division

| Words | Division |
|---|---|
| the quotient of $a$ and $b$ | $a \div b$ |
| $a$ divided by $b$ | $a \div b$ |
| $a$ divided into $b$ equal parts | $a \div b$ |

**Example 4.** Translate and simplify: *the quotient of 144 and 12*.

*Solution.* $144 \div 12 = 12$.

**Try it.** Translate and simplify: *195 divided by 15*.

```answer
Number(13)
```

## Dividing to Solve Problems

*Shared equally*, *each*, *per* and *how many groups* often mean division. Read the question: sometimes a remainder means one more group.

**Example 5.** $138$ students go on a trip in vans that take $12$ each. How many vans are needed?

*Solution.* $138 \div 12 = 11$ R $6$: $11$ vans are full and $6$ students still need a van, so $12$ vans.

**Try it.** A ribbon $96$ inches long is cut into $8$ equal pieces. How long is each piece, in inches?

```answer
Number(12)
```

## Key Concepts

- In $a \div b$, $a$ is the **dividend**, $b$ the **divisor** and the result the **quotient**; what is left over is the **remainder**.
- $a \div 1 = a$; $a \div a = 1$ and $0 \div a = 0$ when $a$ isn't zero; dividing by zero is **undefined**.
- Long division: divide, multiply, subtract, bring down; repeat.
- Check: quotient $\times$ divisor $+$ remainder $=$ dividend.

## Key Terms

**dividend**, **divisor**, **quotient**: in $a \div b = q$, $a$, $b$ and $q$. **remainder**: what is left when the divisor doesn't go exactly.

## Lab

The lab shares counters among groups, one at a time, as you would deal cards. **Run the lab** (F5), set how many counters and how many groups, and press **Deal**: each group fills up in turn, and what can't go round is the remainder.

Then change the program:

1. Find `tmrDeal_Timer` in `Form1`. Make the dealing faster or slower with a slider.
2. Add a **Groups of** mode: instead of sharing among a number of groups, make groups of a given size, and count the groups. It's the same division read another way.

---

Adapted from "1.5 Divide Whole Numbers" in *Prealgebra 2e* by Lynn Marecek, MaryAnne Anthony-Smith and Andrea Honeycutt Mathis (OpenStax), <https://openstax.org/books/prealgebra-2e/pages/1-5-divide-whole-numbers>, licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
