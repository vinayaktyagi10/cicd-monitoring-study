import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "paper", "figures"))
import verify_figures as vf

YML = """name: CI
on:
  push:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
  docker-build:
    needs: test
    steps:
      - uses: docker/build-push-action@v6
"""


def test_workflow_terms_extracts_jobs_actions_and_python_version():
    assert vf.workflow_terms(YML) == ["3.12", "build-push-action", "checkout", "docker-build",
                                      "setup-python", "test"]
