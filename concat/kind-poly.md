# Kind Polymorphism

* Will probably want kind variables in the future
  * Introduce a kind `Kind` at that point
* And kind aliases, too

Probably, the easiest migration is to take the individual variable syntax:

```
`t
```

And use it to mean item-kinded variables instead.

## Prior art

* [Adding kind-polymorphism to the Scala programming language](https://codesync.global/media/adding-kind-polymorphism-to-the-scala-programming-language/)
  * [`AnyKind`](https://www.scala-lang.org/api/current/scala/AnyKind.html)

## Kinds

* (?) Item: the kind of types of stack items
  * Just use Individual?
    * I use kinds for arity checking too, so I think that would make it harder
  * Needed to exclude Sequence from kind-polymorphic type parameters where a
    Sequence is invalid, e.g:
    * `def drop[t : Item](*s t -- *s)` (possible syntax)
* Individual: the kind of zero-arity types of values
* Generic: type constructors
  * they have arities
  * they always construct an individual type
    * I should change this
  * they can be the type of a value, e.g. polymorphic functions
* Sequence: stack types

### Subkinding

```
      Item
    /       \
Individual  Generic


Sequence
```

## Syntax

* `def drop[t : Item](*s t -- *s)`
  * First thing I thought of
  * Looks more natural to me
  * Similar to type parameter syntax for classes
* `def drop(forall (t : Item). (*s t -- *s)):`
  * Uses existing forall syntax, but extended
  * Opens the door to allowing any type syntax as a type annotation
