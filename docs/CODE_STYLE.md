# Code Style Guide

## Abstraction and Design
- Organize code into clear layers:
  1. Configuration (typed settings, constants)
  2. Interface/CLI (logging, config loading, error handling)
  3. Orchestration (wrappers that map config to core calls)
  4. Core Logic (pure data transformations)
  5. Persistence/IO (abstracted behind interfaces)
- Each layer depends only on the layer immediately below and communicates via simple, well-defined interfaces.

## Function Design
- Single responsibility: each function does one thing.
- Keep functions small (aim for ≤50 lines).
- Use explicit type hints for parameters and return values.
- Default parameters for truly optional behavior.
- Name functions with verbs (e.g., `calculate_total`, `filter_newest_snapshot`) and group related operations logically.

## Testing Approach
- Mirror your source directory structure under `tests/`.
- Test pure functions in isolation.
- Use lightweight fakes or mocks to simulate external dependencies (I/O, network).
- Integration tests for end-to-end flows; mark or group them distinctly.
- Name test files and functions to describe the scenario being tested (e.g., `test_filter_returns_newest`).

## Interface and Architecture
- CLI scripts should:
  - Set up logging at the module start.
  - Load configuration via a dedicated settings object.
  - Catch exceptions at the top level, log errors, and exit with non-zero status.
- Keep business logic out of the CLI. Pass only primitives, schemas, and managers into core functions.
- Use factories or dependency injection to obtain resources (e.g., datastore managers).

## Naming Conventions
- snake_case for functions, methods, and variables.
- PascalCase for classes and exceptions.
- UPPER_CASE for constants.
- Descriptive names: reflect purpose rather than implementation details.
- Use f-strings for templated values (filenames, paths), and centralize templates in config or constants.



## Misc
- always use absolute imports
- explicitly re-export from submodules via `__all__=[...]`
-

## Documentation
 - use numpy-style docstrings.
 - use docstrings in all functions.
 - use docstrings in all classes.
 - at the top of each file, include a brief description of the module's purpose and any relevant information about its usage. for all scripts exception cli-modules, they shouldn't be directly called.
