# Testing

We use pytest for all tests.

1. **Test Organization & Naming**
   - Directory structure: `tests/` directory must mirror the source code structure exactly.
   - Test scripts: Place in appropriate `tests/` subdirectory with `test_` prefix (e.g., `test_date_utils.py`).
   - Test functions: Always use `test_<function_name>` (e.g., `test_calculate_isoweeks`).
   - Example:
     ```
     src/utils/date_helpers.py
     → tests/utils/test_date_helpers.py
     ```

2. **Test Focus – Behavior Over Implementation**
   - Test core logic and edge cases (leap years, boundary conditions).
   - Don’t test internal variable names or specific library calls.
   - Do test calculation correctness, error handling, and return‐value formats.
   - Prefer high‐level assertions:
     ```python
     pd.testing.assert_frame_equal(df1, df2)
     ```

3. **Fixtures & conftest.py**
   - Centralize shared setup in `tests/conftest.py`.
   - Scope fixtures appropriately (`function`, `module`, or `session`).
   - Name fixtures descriptively (e.g. `sample_dataframe`, `etl_runner`).
   - Example:
     ```python
     # tests/conftest.py
     import pytest
     import pandas as pd
     from retail_boost_etl.transforms import calculate_isoweeks

     @pytest.fixture(scope="session")
     def sample_dates():
         return ["2020-02-28", "2020-02-29", "2021-01-01"]

     @pytest.fixture
     def df_with_dates(sample_dates):
         return pd.DataFrame({"created_at": pd.to_datetime(sample_dates)})

     @pytest.fixture
     def isoweeks():
         return calculate_isoweeks
     ```

4. **Pytest Best Practices**
   - Use `@pytest.mark.parametrize` for table‐driven scenarios.
   - Group related tests in classes when it improves organization.
   - Follow the Arrange–Act–Assert pattern with clear separation.
   - Keep one logical assertion per test function where practical.

5. **Unit vs Integration Tests**
   - Directory layout:
     ```
     tests/unit/...         # pure function tests
     tests/integration/...  # end‐to‐end pipelines, I/O, external interfaces
     ```
   - Mark integration tests explicitly:
     ```python
     @pytest.mark.integration
     def test_full_pipeline_runs_and_writes(tmp_path, etl_runner):
         etl_runner.run(config, output_dir=tmp_path)
         # assert output files and schema
     ```

6. **Mocking External I/O**
   - Use `monkeypatch` or pytest fixtures to replace GCS, filesystem, or database calls.
   - Keep mocks simple and in‐memory to maintain speed and reliability.
   - Example:
     ```python
     def test_upload_to_gcs(monkeypatch):
         uploads = {}
         def fake_upload(bucket, path, data):
             uploads[(bucket, path)] = data
         monkeypatch.setattr("retail_boost_etl.IO.gcs.upload", fake_upload)
         # invoke upload logic...
         assert uploads
     ```

7. **Flaky Tests & Skips**
   - For non‐deterministic tests, consider `@pytest.mark.flaky(reruns=2)`.
   - Skip platform‐specific or long‐running tests with `@pytest.mark.skip(reason="...")`.

8. **Test Quality & Structure**
   - One logical concept per test.
   - Use meaningful test data representing real‐world scenarios.
   - Cover boundary conditions (empty inputs, `None`, etc.) and error states.

9. **What Makes a Good Test**
   - **Independent**: order doesn’t matter.
   - **Fast**: avoid heavy I/O; mock external deps.
   - **Reliable**: same input → same output.
   - **Readable**: other devs can understand intent.
   - **Focused**: one specific behavior or edge case.

10. **Test Coverage Strategy**
    - Prioritize critical business logic, error paths, and edge cases over 100% line coverage.
    - Enforce a minimum coverage threshold in CI (e.g., 80%) without obsessing over every line.
