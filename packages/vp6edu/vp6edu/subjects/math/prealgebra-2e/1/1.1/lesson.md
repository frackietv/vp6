# 1.1 Introduction to Whole Numbers

## Learning Objectives

- Tell counting numbers and whole numbers apart.
- Show a whole number with base-10 blocks.
- Find the place value of a digit.
- Name a whole number in words.
- Write a whole number from its name.
- Round a whole number to a given place.

## Be Prepared

This is where the path starts: all you need is to be able to count. Before you begin, count the stars.

★ ★ ★ ★ ★ ★ ★ ★ ★

```answer
Number(9)
```

## Counting Numbers and Whole Numbers

The numbers we first learn to count with, $1, 2, 3, 4, \ldots$, are the **counting numbers**. The three dots mean the list goes on for ever: there is no largest counting number.

Put $0$ in front of them and you have the **whole numbers**: $0, 1, 2, 3, \ldots$. Every counting number is a whole number, and zero is the one whole number that isn't a counting number. A fraction such as $\frac{3}{4}$ or a decimal such as $2.5$ is neither.

On a **number line** the whole numbers are equally spaced marks, $0$ at the left, getting larger to the right.

**Example 1.** Which of the numbers $0$, $7$, $2.5$, $12$, $\frac{3}{4}$ and $100$ are counting numbers, and which are whole numbers?

*Solution.* The counting numbers start at $1$: $7$, $12$ and $100$. The whole numbers are those and $0$: $0$, $7$, $12$ and $100$. Neither list has $2.5$ or $\frac{3}{4}$.

**Try it.** Which one of these is a whole number but not a counting number? (A) $1$ (B) $0$ (C) $\frac{1}{2}$ (D) $10$

```answer
Choice("B", ["1", "0", "1/2", "10"])
```

## Modelling Whole Numbers

We write numbers with ten **digits**, $0$ to $9$, and where a digit stands tells what it is worth. Base-10 blocks show this: a small cube is $1$; a rod of ten cubes is $10$; a flat of ten rods is $100$; a big cube of ten flats is $1{,}000$.

**Example 2.** What number do 2 flats, 3 rods and 6 cubes show?

*Solution.* 2 flats are $200$, 3 rods are $30$ and 6 cubes are $6$: together $236$.

**Try it.** What number do 3 flats, no rods and 8 cubes show?

```answer
Number(308)
```

## Place Value

Each place is worth ten times the place to its right. From the right: ones, tens, hundreds; then the same three again for thousands, millions and billions. Each group of three is a **period**, and in a long number commas separate the periods.

| Billions | | | Millions | | | Thousands | | | Ones | | |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hundred | ten | one | hundred | ten | one | hundred | ten | one | hundred | ten | one |

**Example 3.** In $5{,}284{,}097$, what is the place value of each digit?

*Solution.* Reading from the left: $5$ millions, $2$ hundred thousands, $8$ ten thousands, $4$ thousands, $0$ hundreds, $9$ tens and $7$ ones.

**Try it.** Which digit is in the ten thousands place of $6{,}915{,}342$?

```answer
Number(1)
```

## Naming Whole Numbers

To say a number in words:

1. Split it into periods from the right.
2. Name the number in each period, from the left, followed by the period's name (but not "ones").
3. Put a comma after each period's name.

Numbers from twenty-one to ninety-nine take a hyphen, and we never say "and" in a whole number.

**Example 4.** Name $7{,}045{,}312$ in words.

*Solution.* The periods are $7$ millions, $045$ thousands and $312$ ones: *seven million, forty-five thousand, three hundred twelve*.

**Try it.** Which is the name of $30{,}506$? (A) thirty thousand, fifty-six (B) three thousand, five hundred six (C) thirty thousand, five hundred six (D) thirty thousand, five hundred sixty

```answer
Choice("C", ["thirty thousand, fifty-six", "three thousand, five hundred six", "thirty thousand, five hundred six", "thirty thousand, five hundred sixty"])
```

## Writing Whole Numbers from Their Names

Going the other way, find the largest period named, then write each period's three digits, filling the places nobody named with zeros.

**Example 5.** Write *fourteen million, two hundred thousand, sixty-three* with digits.

*Solution.* The millions period is $14$; the thousands period is $200$; the ones period is $063$. So $14{,}200{,}063$.

**Try it.** Write *nine thousand, forty* with digits.

```answer
Number(9040)
```

## Rounding

Often we don't need a number exactly: "about $3{,}800$ people" says enough. **Rounding** finds the nearest number with zeros after a given place.

1. Find the digit in the place you are rounding to.
2. Look at the digit just to its right. If it is $5$ or more, add one to the digit in your place; if it is less than $5$, leave the digit as it is.
3. Replace every digit to the right of your place with zeros.

On a number line, $3{,}846$ lies between $3{,}800$ and $3{,}900$, just before the halfway mark $3{,}850$, so it is nearer $3{,}800$. A number exactly halfway rounds up.

**Example 6.** Round $3{,}846$ to the nearest hundred, then to the nearest ten.

*Solution.* The hundreds digit is $8$ and the digit to its right is $4$, less than $5$: $3{,}800$. The tens digit is $4$ and the digit to its right is $6$, $5$ or more: $3{,}850$.

**Try it.** Round $72{,}593$ to the nearest thousand.

```answer
Number(73000)
```

**Try it.** Round $1{,}996$ to the nearest ten. (Adding one to the $9$ carries into the next place.)

```answer
Number(2000)
```

## Key Concepts

- The **counting numbers** are $1, 2, 3, \ldots$; the **whole numbers** are $0, 1, 2, 3, \ldots$.
- A digit's **place value** is what its place is worth: ones, tens, hundreds, then thousands, millions and billions, each a **period** of three places.
- To **name** a number, name each period's number and then the period, left to right, with commas; leave out "ones".
- To **round**, look at the digit to the right of the place: $5$ or more rounds up, less than $5$ rounds down; the places after it become zeros.

## Key Terms

**digit**: one of the ten symbols $0$ to $9$ that numbers are written with.

**period**: a group of three places (ones, thousands, millions, billions).

**rounding**: replacing a number by the nearest one with zeros after a given place.

## Lab

The lab is a place-value chart. **Run the lab** (F5), drag digits from the row of tiles into the chart's places, and watch the number, its name and its expanded form change. Click a place to empty it. Choose a place in **Round to** and the number line shows the two numbers it could round to, the halfway mark and which one wins.

Then change the program:

1. Open `Form1` and find `name_of`, which names a number in words. Name a few numbers in the lab and check its names against the rules above.
2. Add *billions* to the chart: a place-value box needs a heading, a drop target and a place in `PLACES`.
3. Add *Random* rounding practice: a button that fills the chart with random digits and asks for the number rounded to a random place.

---

Adapted from "1.1 Introduction to Whole Numbers" in *Prealgebra 2e* by Lynn Marecek, MaryAnne Anthony-Smith and Andrea Honeycutt Mathis (OpenStax), <https://openstax.org/books/prealgebra-2e/pages/1-1-introduction-to-whole-numbers>, licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
