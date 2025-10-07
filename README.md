# data_validation

Minimal project for data validation.

Getting started

1. Ensure Poetry is installed (we detected Poetry 2.x is available).
2. Create the project venv and install default dependencies:

```cmd
poetry config virtualenvs.in-project true --local
poetry install
```

3. Add dependencies:

```cmd
poetry add <package>
poetry add --dev pytest
```

4. Use the environment:

```cmd
poetry shell
poetry run python -m pytest
```
