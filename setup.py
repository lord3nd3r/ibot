"""Setup configuration for ibot."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="ibot",
    version="1.0.0",
    author="Your Name",
    description="A lightweight, asyncio-powered IRC bot with Sopel plugin compatibility",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/ibot",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Communications :: Chat :: Internet Relay Chat",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.8",
    install_requires=[
        "sqlalchemy>=2.0.0,<3.0.0",
    ],
    extras_require={
        "mysql": ["pymysql>=1.0.0"],
        "postgres": ["psycopg2-binary>=2.9.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "ibot=ibot.__main__:main",
        ],
    },
    include_package_data=True,
)
