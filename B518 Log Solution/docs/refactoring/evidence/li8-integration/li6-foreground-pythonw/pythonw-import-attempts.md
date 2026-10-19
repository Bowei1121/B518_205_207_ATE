# LI6 pythonw setup attempts

The first `pythonw` invocation did not set `PYTHONPATH` and failed before loading the test: `ModuleNotFoundError: No module named 'b518_log_solution'`.

The second invocation used `PYTHONPATH=src` and failed before loading the test body: `ModuleNotFoundError: No module named 'test_log_solution_ui'`.

The final run used `PYTHONPATH=src:tests`, entered the acceptance test and reached the same final restore assertion as the python3 candidate and baseline runs. Its raw output is in `pythonw-run.log`. The failed setup attempts are not counted as acceptance results.
