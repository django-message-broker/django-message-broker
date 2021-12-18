import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="Django Message Broker",
    version="0.1.0",
    author="David Plummer",
    author_email="david.plummer@tanzo.org",
    license="BSD 3-Clause",
    keywords="django message broker channels celery",
    description="A django extension providing an integrated message broker supporting interprocess communication.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DiaAzul/django-message-broker",
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Programming Language :: Python :: 3.8",
        "Framework :: Django :: 3.2",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Typing :: Typed"
    ],
    python_requires='>=3.8',
    install_requires=[
        "Django>=3.2.0",
        "msgspec>=0.3.0",
        "pyzmq>=22.3.0",
        "tornado>=6.1",
    ]
)
