"""Setup script for concat."""
from setuptools import setup, find_packages

setup(
    name='concat',
    version='0.1.1',
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
        'Programming Language :: Python :: 3.5',
    ],
    keywords='concatenative',
    packages=find_packages(),
    install_requires=['ply>=3.7,<4', 'astunparse>=1.3.0,<2'],
    test_suite='nose.collector',
    tests_require=['nose', 'scripttest']
)
