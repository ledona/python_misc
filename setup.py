from setuptools import find_packages, setup

setup(
    name="ledona",
    version="2024.03.29",
    description="Assorted useful stuff for my python projects",
    packages=find_packages(),
    install_requires=(
        # gsheet stuff
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
        # for base test class
        "pandas",
    ),
)
