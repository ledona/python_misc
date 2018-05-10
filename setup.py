from setuptools import setup, find_packages

setup(
    name='ledona',
    version='0.1',
    description='Assorted useful stuff for my python projects',
    packages=find_packages(),
    install_requires=(
        'google-api-python-client',

        # for base test class
        'pandas')
)
