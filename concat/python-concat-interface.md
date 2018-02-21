Python-Concat Interface
=======================

Into Python from Concat
-----------------------

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

Into Concat from Python
-----------------------

Python code may call a Concat function by passing a stack and stash (both lists) to it. The
function will modify that stack. For example,

```python
from libconcat import pop

stack = [1, 2, 5, 'Three, sir!']
pop(stack, [])
print(stack)  # [1, 2, 5]
```
