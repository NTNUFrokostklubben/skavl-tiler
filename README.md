# SKAVL tiler

This is a module that communicates with the SKAVL application to generate tilesets from geotif and a given viewport resolution for easier display

## Build

### Windows

To build this application for windows first create a conda environment based on the environment.yaml file
```shell
conda env create -f .\environment.yaml -n env-name
```
After the environment is created, make sure to activate it using
```shell
conda activate env-name
```
Now the installation command can be initiated
```shell
pyinstaller server.spec
```
This will build and bundle all the required files in the dist/server folder. 
The application can now be run from the .exe

## License
Open-source: AGPL-3.0 (see LICENSE)
Commercial: available on inquiry (see COMMERCIAL.md)