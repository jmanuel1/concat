Concat
======

An experimental concatenative Python-based programming language.

Examples are in the examples directory. To see the spec, go to
[http://jmanuel1.github.io/concat-spec/](http://jmanuel1.github.io/concat-spec/).

Python 3.7+ required.

Building and uploading (on Windows)
---------------------

Change the version number in `setup.py`. **Upload will fail if you try to push
an existing version.**

Delete the `dist` directory, if it exists.

    rmdir dist /S

Build source and pure Python-3 distributions.

    py -3 setup.py sdist
    py -3 setup.py bdist_wheel

Upload.

    twine upload dist/* [-r pypitest]

Testing
-------

Run the tests under `coverage.py`:

    pip install coverage
    coverage run setup.py test

Combine the coverage data:

    coverage combine

**Nota Bene**: If you have `concat` installed globally, make sure to create and
enter a `virtualenv` before testing, so you don't end up running the installed
version.

Summer of Shipping *aspirational* project goals
-------------

1. Clean up some uglier and overly repetitive parts of the code.
   - In particular, the transpiler tests should be rewritten or gotten rid of.
     They don't test what was meant to be tested (that correct Python ASTs are
     produced) anyway.
2. Make the project more amenable to collaboration.
   - Automated testing
   - Testing coverage
   - Code formatter & linter
   - Code quality analysis?
3. Simplify type checking or skip it all together (for now).
4. Settle on some minimal core language to make functional. The language has
   been growing a lot, and perhaps efforts should be more focused instead.
5. Create an online demo.

Related work
------------

For a similar idea that is more mature, check out
[Nustack](https://github.com/BookOwl/nustack).
