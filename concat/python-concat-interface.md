Python-Concat Interface
=======================

Into Python from Concat
-----------------------

### Function interface

Concat code may call a function that was written in Python.

* If that function is decorated with `@ConcatFunction`, it will be treated as a
function written in Concat.
* Otherwise, it will be treated as if it had the stack effect `args kwargs --
func(*args, **kwargs)`, where `args` is a list of positional arguments and
`kwargs` is a dictionary of keyword arguments.

Before (e.g. in commit `2885487c289ceeb4663f12894ba732d1b833fee7`), complex
attempted conversions, checks, and overrides were performed, but this system is
better for its simplicity. It could be simplified further by requiring Python
functions to be called with some special function, but the current system
avoids that.

### Object interface

Before entering Python code, non-callable objects are replaced with the result
of the `pythonify` function. This function calls the `_pythonify_` method.
Concat classes override the method as they see fit. In `ConcatObject`, the
method returns `self`. If the object is not a Concat object, it is left untouched.

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

### Object interface

Before entering Concat code, non-callable objects should be wrapped in the
`concatify` function. The function looks up the target class in the
`concatify.table` dictionary using the original class as a key. The result is
`<target class>._concatify_(<original object>)`. If there is no matching key in the
dictionary, the object is left untouched.
