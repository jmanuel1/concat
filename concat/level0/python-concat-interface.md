Python-Concat Interface
=======================

Into Python from Concat
-----------------------

### Function interface

The following is true at level 0.

Concat code may call a function that was written in Python.

Python functions must be called with the function `py_call` from
`concat.level0.stdlib.pyinterop`. This approach has the advantages of being
easier to implement and having more explicit behavior. To quote the Zen of
Python, "explicit is better than implicit."

`py_call` has the stack effect `sequence_of_pairs sequence $function --
return_value`. `sequence_of_pairs` and `sequence` correspond to keyword
arguments and positional arguments, respectively.

#### Examples

```python
# Based on examples from https://learnxinyminutes.com/docs/python3/
$() $(0) $bool py_call  # => False
$() $('This is a string') $len py_call  # => 16
$() $('Strings' 'interpolated') '{} can be {}'$.format py_call
```

#### Historical notes

Before, (e.g. in commit `6d7376c`), we used the following logic:

* If that function is decorated with `@ConcatFunction`, it will be treated as a
  function written in Concat.
* Otherwise, it will be treated as if it had the stack effect `args kwargs --
  func(*args, **kwargs)`, where `args` is a list of positional arguments and
  `kwargs` is a dictionary of keyword arguments.

Even further in the past, (e.g. in commit
`2885487c289ceeb4663f12894ba732d1b833fee7`), complex attempted conversions,
checks, and overrides were performed.

Into Concat from Python
-----------------------

### Function interface

Python code may call a Concat function by passing a stack and stash (both
lists) to it. The function will modify that stack. For example,

```python
from libconcat import pop

stack = [1, 2, 5, 'Three, sir!']
pop(stack, [])
print(stack)  # [1, 2, 5]
```
