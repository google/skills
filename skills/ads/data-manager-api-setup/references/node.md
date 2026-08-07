# Node Client and Utility Library Installation

## Install Client Library

Install the Node.js client library:

```shell
npm install @google-ads/datamanager
```

## Install Utility Library

> [!IMPORTANT]
> The companion utility libraries are not available on public package managers
> (such as npm). Follow the instructions below to clone and install the library.

1.  Clone the repository:
    ```shell
    git clone https://github.com/googleads/data-manager-node.git
    ```

2.  Navigate to the `data-manager-node` directory and install dependencies:
    ```shell
    npm install
    ```
3.  Navigate to the `util` directory:
    ```shell
    cd util
    ```
4.  Pack the utility library into a `.tgz` archive:
    ```shell
    npm pack
    ```
5.  Declare a dependency in your Node.js project's `package.json` pointing to
    the path of the generated `.tgz` archive:
    ```json
    {
       "dependencies": {
          "@google-ads/data-manager-util": "file:{path_to_archive}"
       }
    }
    ```
