from setuptools import find_packages, setup

setup(
    name="ledona",
    version="2025.12.23",
    description="Assorted useful stuff for my python projects",
    packages=find_packages(),
    install_requires=(
        # TODO: a could things missing from here
        # gsheet stuff
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
        # for base test class
        "pandas",
    ),
)
