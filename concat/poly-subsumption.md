Subsumption of a polymorphic type by another type may involve instantiation and
reordering of type variables. Subsumption can be checked using
"regeneralization."

I think a correct(-ish?) way of doing regeneralization in Concat is the
following (substitution notation might be backwards):

```
            t[fresh(a+)/a+] <: s with b+ rigid   
            b+ all not in ftv(forall a+. t)     
------------------------------------------------------ [FORALL<:FORALL]
            forall a+. t <: forall b+. s
```

In the `HMV_InstG` rule of [Visible Type Application (Extended
version)](https://www.seas.upenn.edu/~sweirich/papers/type-app-extended.pdf), in
Fig. 4, there's a condition that the bs are not free in `forall a.... t`.

`FORALL<:FORALL` means that `forall a. int <: forall a, b. int`. But `forall (a :
Individual). a /<: forall (b : Item). b` because we would have to solve
`fresh(a) <: b`, which requires the substitution `[b/a]` because the kind of
`b` >= the kind of `a`. But we made `b` rigid!

```
  (s can be generic, but not a forall)
    forall a+, b*. t : Generic[k+, l*]
           s : Generic[m*]
              l* :> m*
     forall b*. t[fresh(a+)/a+] <: s
---------------------------------------- [FORALL<:INST]
         forall a+, b*. t <: s

    (b is a unification variable)
     forall a+. t : Generic[k+]
             b : l
         Generic[k+] <: l
-------------------------------------- [FORALL<:VAR]
forall a+. t <: b --> [b/forall a+. t]
```

The following might not make sense:

```
(s can be generic, but not a forall)
    forall a+. t : Generic[k+]
              s : l
          Generic[k+] <: l
          b+ = fresh(a+)
t[b+/a+] <: s[b+] (type application)
------------------------------------ [FORALL<:KIND-SUB]
        forall a+. t <: s
```

Other papers mentioning regeneralization:
- [Guarded impredicative polymorphism](https://www.microsoft.com/en-us/research/uploads/prod/2017/07/impred-pldi18-submission.pdf)
