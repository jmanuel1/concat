Concat
======

An experimental concatenative Python-based programming language.

Examples are in the examples directory. To see the spec, go to
[http://jmanuel1.github.io/concat-spec/](http://jmanuel1.github.io/concat-spec/).


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

Related work
------------

For a similar idea that is more mature, check out
[Nustack](https://github.com/BookOwl/nustack).
