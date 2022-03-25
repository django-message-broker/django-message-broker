# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2022-01-26: Refactor client for better maintenance

### Added

+ Add PULL command to client.
+ Add decorator to associate messaging commands with functions.

### Changed

+ Migrated Django channels from Subscribe/Receive to Pull command.

## [0.2.0] - 2021-12-18: Documentation and testing

### Added

+ Sphinx documentation for Read The Docs.
+ Add test cases

### Changed

+ Nothing

## [0.1.0] - 2021-12-18: Initial commit.

### Added

+ Initial code prior to packaging for PyPi.
+ Interface for django channels.
+ Interface for background worker.

### Changed

+ Nothing
