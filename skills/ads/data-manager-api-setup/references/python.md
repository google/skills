# Python Client and Utility Library Installation

## Install Client Library

Install the Python client library:

```shell
pip install google-ads-datamanager
```

## Install Utility Library

> [!IMPORTANT]
> The companion utility libraries are not available on public package managers
> (such as PyPI). Follow the instructions below to clone and install the
> library.

1.  Clone the repository:
    ```shell
    git clone https://github.com/googleads/data-manager-python.git
    ```
2.  Determine the latest version of the library (`{version}`) in
    `pyproject.toml` (e.g., `0.1.0`).
3.  Navigate to the `data-manager-python` directory and install the utility
    library:
    ```shell
    pip install .
    ```
4.  Declare a dependency in your project's `requirements.txt` file. Replace
    `{version}` with the value found in step 2.
    ```
    google-ads-datamanager-util=={version}
    ```
