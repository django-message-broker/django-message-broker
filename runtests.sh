#!/bin/bash

python -m venv .venv
source .venv/activate
python -m pip install -e .
python -m pip install -r requirements.txt
python -m unittest discover -s ./tests
tests/runtests.py