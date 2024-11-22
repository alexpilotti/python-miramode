from setuptools import setup, find_packages

setup(
    name="python-miramode",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[line.strip() for line in
                      open("requirements.txt").readlines()],
    entry_points={
        'console_scripts': [
            'miramodecli = miramode.cli:main',
        ],
    },
    author="Alessandro Pilotti",
    description=("A Python module and CLI to automate Mira Mode digital "
                 "showers"),
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/alexpilotti/python-miramode",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.9',
)
