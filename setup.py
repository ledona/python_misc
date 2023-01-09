from setuptools import setup, find_packages

setup(
    name='ledona',
    version='2023.01.08',
    description='Assorted useful stuff for my python projects',
    packages=find_packages(),
    install_requires=(
        # gsheet stuff
        'google-api-python-client',
        'google-auth-httplib2',
        'google-auth-oauthlib',

        # for base test class
        'pandas',
    )
)
