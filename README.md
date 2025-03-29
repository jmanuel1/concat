Concat
======

[![Coverage
Status](https://coveralls.io/repos/github/jmanuel1/concat/badge.svg?branch=master)](https://coveralls.io/github/jmanuel1/concat?branch=master)

An experimental concatenative Python-based programming language.

Examples are in the examples directory. To see the (out of date and incomplete)
spec, go to
[http://jmanuel1.github.io/concat-spec/](http://jmanuel1.github.io/concat-spec/).

Python 3.12 required.

Development
-----------

### Code formatting

Python code is formatted using [Ruff](https://docs.astral.sh/ruff/) through a
[pre-commit](https://github.com/pre-commit/pre-commit) Git hook. To set this up
in your clone of the repository, install the `dev` dependencies of the project
(by running `pip install -e .[dev]`, for example), and then run:

    pre-commit install

Now Ruff and pre-commit should be working! Whenever you commit a Python file,
Ruff will be ran on that file. If Ruff makes formatting changes, you might need
to try restaging and recommiting.

### Testing

If you run the tests on Windows, you might need a
[Rust](https://www.rust-lang.org) installation for one of the tests. (The tests
depend on [`pywinpty`](https://pypi.org/project/pywinpty/) to use Windows
pseudoterminals.)

If your Python is 32-bit, you may get Rust compile errors that make it look like
the standard library is missing (in particular, E0463: `rustc --explain E0463`).
As suggested by `rustc`, you can try adding the right standard library with
`rustup target add <target>`. I used the target `i686-pc-windows-msvc` even
though `pywinpty` claims to require `x86_64-pc-windows-msvc` to build from
source. Then set the environment variable `CARGO_BUILD_TARGET` to
`i686-pc-windows-msvc` and try to install `pywinpty` again.

Run the tests and get coverage info using `coverage run -m nose2 --pretty-assert
concat.tests`. (Make sure you've installed the development dependencies first.)

**Nota Bene**: If you have `concat` installed globally, make sure to create and
enter a `virtualenv` before testing, so you don't end up running the installed
version.

### CI Linters

To run the linters locally, use:

```pwsh
# Powershell
docker run -e RUN_LOCAL=true --env-file .\.github\super-linter.env -v .:/tmp/lint ghcr.io/super-linter/super-linter:latest
```

### Building and uploading (on Windows)

Change the version number in `setup.py`. **Upload will fail if you try to push
an existing version.**

Delete the `dist` directory, if it exists.

    rmdir dist /S

Build source and pure Python-3 distributions.

    py -3 setup.py sdist
    py -3 setup.py bdist_wheel

Upload.

    twine upload dist/* [-r pypitest]

Related work
------------

For a similar idea that is more mature, check out
[Nustack](https://github.com/BookOwl/nustack).
