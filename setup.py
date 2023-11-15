import re
from setuptools import setup, find_packages


VERSION = '0.0.1'


with open("README.md", "r") as readme:
    long_description = readme.read()

setup(
    name="bigraph-builder",
    version=VERSION,
    author="Eran Agmon",
    author_email="agmon.eran@gmail.com",
    description="",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/vivarium-collective/bigraph-builder",
    packages=find_packages(),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.6",
    install_requires=[
        # List your package dependencies here
        "process-bigraph",
        "bigraph-viz"
    ],
)
