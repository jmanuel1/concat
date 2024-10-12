The type constructor of a type application is restricted to being a name.

```python
{
    seed: py_function[(int), none],
    shuffle: forall `t. py_function[(list[`t]), none]
}
```

```
Object
  seed:
    type application
      name - py_function
      args
        sequence
          item 1:
            name - _
            name - int
        name - none
  shuffle:
    forall
      args
        individual var - t
      type
        type application
          name - py_function
          args
            sequence
              item 1:
                name - _
                type application
                  name - list
                  args
                    individual var - t
            name - none
```  
