import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="healthdes", # Replace with your own username
    version="0.0.2",
    author="David Plummer",
    author_email="david.plummer@tanzo.org",
    license="BSD 3-Clause",
    keywords="library simulation healthcare health care hospital",
    description="A python library to support discrete event simulation in health and social care",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/DiaAzul/healthdes",
    packages=setuptools.find_packages(),
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",        
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Intended Audience :: Healthcare Industry",
        "Topic :: Software Development :: Libraries"
    ],
    python_requires='>=3.7',
    install_requires=['simpy>=4',
                      'networkx>=2',
                      'pandas>=1']
)