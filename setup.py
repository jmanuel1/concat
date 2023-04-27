"""Setup script for concat."""
from setuptools import setup, find_packages  # type: ignore
import concat

setup(
    name='concat',
    version=concat.version,
    description='An experimental concatenative Python-based programming language',  # noqa
    long_description=open('README.md').read(),
    url='https://github.com/jmanuel1/concat',
    author='Jason Manuel',
    author_email='jama.indo@hotmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Interpreters',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.7',
    ],
    keywords='concatenative',
    packages=find_packages(),  # type: ignore
    install_requires=[
        'astunparse>=1.3.0,<2',
        'parsy>=1.3.0,<2',
        'typing-extensions>=4',
    ],
    test_suite='nose.collector',
    tests_require=[
        'coverage>=6.4.4,<7',
        'hypothesis==5.38.0',
        # NOTE: If you upgrade hypothesis, you might be able to remove this.
        'importlib-metadata<5.0',
        'nose',
        'pywinpty>=2.0.7,<3; platform_system=="Windows"',
        'scripttest',
    ],
    extras_require={
        'dev': ['axblack==20220330', 'mypy>=1.1.1', 'pre-commit>=2.6.0,<3']
    },
)
