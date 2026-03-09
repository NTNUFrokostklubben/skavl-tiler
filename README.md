# SKAVL tiler

This is a module that communicates with the SKAVL application to generate tilesets from geotif and a given viewport resolution for easier display

## Running and Building

Building this application is relatively platform-agnostic, but it requires that conda is installed and that [conda-lock](https://github.com/conda/conda-lock) is installed.
One of the easiest ways of installing this is to install it on the base conda environment. 
```shell
conda install -n base -c conda-forge conda-lock
```

Install the conda environment from the lockfile (skavl-tiler-build should be replaced with whatever environment name you want to use in conda)
```shell
conda-lock install -n skavl-tiler-build .\conda-lock.yml
```
Verify that an environment was created
```shell
conda env list
```
If the environment exists, activate it (replace skavl-tiler-build with the actual env name)
```shell
conda activate skavl-tiler-build
```
### Run

Once the environment is active the project can be run via the server.py interface. By default
```shell
python src/server.py
```

### Build

Once activated, build for the platform you are currently on
```shell
pyinstaller server.spec
```
The `server.spec` file should handle linux/windows lib linking automatically, however this is not tested very thoroughly.
Once the build is finished, it should be present under dist/server in the root of the project. 

## Expanding

If more packages are required from conda it is important that these are added manually to the environment.yaml file and that a new conda-lock.yml file is generated.
Exporting the environment will cause multiple platform specific packages to be included in the environment.yaml file which breaks cross-compiling.


Once a module has been installed and added manually to environment.yaml, run the following command to generate the new conda-lock.yml file.
```shell
conda-lock -f environment.yaml -p win-64 -p linux-64
```

When install the new lock-file has been created, verify that a new environment can be created from it using conda-lock install.
Also check that the project builds and that it runs.

## License
Open-source: AGPL-3.0 (see LICENSE)
Commercial: available on inquiry (see COMMERCIAL.md)