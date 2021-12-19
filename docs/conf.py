import os
import re
import sys
from pathlib import Path
from shutil import copy2
# from recommonmark.parser import CommonMarkParser

# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
sys.path.insert(
    0,
    str(
        Path(
            str(Path(__file__).parent.parent)
        ).resolve()
    )
)
sys.setrecursionlimit(1500)

# -- Copy assets from outside docs to temporary assests folder -----------------
# The docs assets folder is not replicated in git.

asset_list = [
    "CHANGELOG.md",
    "assets/django_message_broker_icon_512.svg",
    "assets/django_message_broker_icon_512.png",
]
basedir = Path(__file__).parent.parent
target_directory = basedir / "docs" / "assets"
for asset in asset_list:
    source_file = basedir / asset
    filename = os.path.basename(source_file)
    destination_file = target_directory / filename
    copy2(source_file, destination_file)

# -- Project information -----------------------------------------------------

project = 'Django Message Broker'
copyright = '2021, Tanzo Creative Ltd'
author = 'Tanzo Creative Ltd'

# The full version, including alpha/beta/rc tags
with open("../django_message_broker/__init__.py", "rb") as f:
    release = str(re.search('__version__ = "(.+?)"', f.read().decode()).group(1))
version = release.rpartition(".")[0]

# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.napoleon',
    'sphinx.ext.coverage',
    'sphinx_rtd_theme',
    "myst_parser"  # ,
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = "sphinx_rtd_theme"
html_theme_path = ["_themes", ]

html_logo = "assets/django_message_broker_strap_192.png"
html_theme_options = {
    "logo_only": True,
    "display_version": False,
}


# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = False
napoleon_use_admonition_for_notes = False
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None
