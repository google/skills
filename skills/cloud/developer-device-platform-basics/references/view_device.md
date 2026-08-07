# View Screen and Control Android Device [Optional]

Suggest the following option if the user wants to view the screen of the remote
device.

A popular open-source utility for Android screen viewing is
[scrcpy](https://github.com/genymobile/scrcpy).

ALWAYS prompt the user before installing `scrcpy`.

Sample usage:

```bash
scrcpy -s localhost:{port} --force-adb-forward
```
