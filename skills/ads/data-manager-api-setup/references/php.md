# PHP Client and Utility Library Installation

## Install Client Library

Install the `googleads/data-manager` component using Composer:

```shell
composer require googleads/data-manager
```

## Install Utility Library

> [!IMPORTANT]
> The companion utility library is not available on Packagist. Follow the
> instructions below to clone and install the library.

1.  Clone the repository:
    ```shell
    git clone https://github.com/googleads/data-manager-php.git
    ```
2.  Navigate to the `data-manager-php` directory.
3.  Resolve dependencies for the library:
    ```shell
    composer update --prefer-dist
    ```
4.  Update your project's `composer.json` to declare a dependency on the
    utility library using a path repository:
    ```json
     {
         "repositories": [
             {
                 "type": "path",
                 "url": "{path_to_repository}"
             }
         ],
         "require": {
             "googleads/data-manager-util": "@dev"
         }
     }
    ```
