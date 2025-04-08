# CONTRIBUTING

## Contributing to Dubbo Python

Dubbo Python is released under the non-restrictive Apache 2.0 licenses and follows a very standard Github development process, using Github tracker for issues and merging pull requests into main. Contributions of all form to this repository is acceptable, as long as it follows the prescribed community guidelines enumerated below.

### Sign the Contributor License Agreement

Before we accept a non-trivial patch or pull request (PRs), we will need you to sign the Contributor License Agreement. Signing the contributors' agreement does not grant anyone commits rights to the main repository, but it does mean that we can accept your contributions, and you will get an author credit if we do. Active contributors may get invited to join the core team that will grant them privileges to merge existing PRs.

### Contact

### Mailing list

The mailing list is the recommended way of pursuing a discussion on almost anything related to Dubbo. Please refer to this [guide](https://github.com/apache/dubbo/wiki/Mailing-list-subscription-guide) for detailed documentation on how to subscribe.

- [dev@dubbo.apache.org](mailto:dev-subscribe@dubbo.apache.org): the developer mailing list where you can ask questions about an issue you may have encountered while working with Dubbo.
- [commits@dubbo.apache.org](mailto:commits-subscribe@dubbo.apache.org): the commit updates will get broadcasted on this mailing list. You can subscribe to it, should you be interested in following Dubbo's development.
- [notifications@dubbo.apache.org](mailto:notifications-subscribe@dubbo.apache.org): all the Github [issue](https://github.com/apache/dubbo/issues) updates and [pull request](https://github.com/apache/dubbo/pulls) updates will be sent to this mailing list.

### Reporting issue

Please follow the [template](https://github.com/apache/dubbo/issues/new?template=dubbo-issue-report-template.md) for reporting any issues.

NOTE: Issues related to Dubbo Python should be submitted in the [Dubbo](https://github.com/apache/dubbo/issues) repository, and the **Apache Dubbo Component** option should be set to `Python SDK`.

### Code Conventions

Our code style almost fully adheres to the [**PEP 8 style guide**](https://peps.python.org/pep-0008/), with the following adjustments and new constraints:

1. We have relaxed the **Maximum Line Length** limit from 79 to **120**.
2. For **Documentation Strings**, or **comment style**, we follow the `reStructuredText` format.
3. ...

### Contribution flow

A rough outline of an ideal contributors' workflow is as follows:

- Fork the current repository
- Create a topic branch from where to base the contribution. Mostly, it's the main branch.
- Make commits of logical units.
- Make sure the commit messages are in the proper format (see below).
- Push changes in a topic branch to your forked repository.
- Follow the checklist in the [pull request template](https://github.com/apache/dubbo-python/blob/main/.github/PULL_REQUEST_TEMPLATE.md)
- Before sending out the pull request, please sync your forked repository with the remote repository to ensure that your PR is elegant, concise. Reference the guide below:

```
git remote add upstream git@github.com:apache/dubbo-python.git
git fetch upstream
git rebase upstream/master
git checkout -b your_awesome_patch
... add some work
git push origin your_awesome_patch

```

- Submit a pull request to apache/dubbo-python and wait for the reply.

Thanks for contributing!



### Development & Testing

Before you start working on development, please install the necessary dependencies for Dubbo-Python using the following command:

```shell
pip install -r requirements-dev.txt
```

Our project uses a `src` layout, and packaging is required before running tests. We strongly recommend using the **editable installation mode** for packaging and testing:

```shell
pip install -e .
```



### Code style

We use **ruff** as the linter and code formatter for Dubbo-Python, and **Mypy** as the static type checker.

Therefore, when developing, you should install both tools:

- ruff: [https://github.com/astral-sh/ruff](https://github.com/astral-sh/ruff)
- Mypy: [https://github.com/python/mypy](https://github.com/python/mypy)

We have already set up the configurations for ruff and Mypy in the `pyproject.toml` file. You only need to specify the configuration path (`pyproject.toml`) when using them.

1. Code Formatting
   
    By default, ruff will look for the `pyproject.toml` file in the current directory and its parent directories and load its configuration.
    
    ```shell
    # Default
    ruff format
    
    # Specify configuration file
    ruff format --config pyproject.toml
    ```
    
2. Code Linting
   
    ```shell
    # Just check
    ruff check
    
    # Check and fix
    ruff check --fix
    ```
    
3. Static Type Checking
   
    Mypy will also automatically look for the `pyproject.toml` file and load its configuration.
    
    ```shell
    # Default
    mypy
    
    # Specify configuration file
    mypy --config-file pyproject.toml
    ```