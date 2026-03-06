import os

import numpy as np
from osgeo import gdal
from PIL import Image
from typing_extensions import deprecated


def extract_bands(data_source, selected_level: int) -> list:
    """Extract all bands from a GeoTIFF.

    Args:
        data_source: GDAL datasource from gdal.Open or gdal.OpenEx
        selected_level: Logical quality level where l0 is full resolution and higher level is lower resolution.

    Returns:
        list of GDALRasterBand
    """
    bands = []
    for band_index in range(1, data_source.RasterCount + 1):
        band = data_source.GetRasterBand(band_index)
        if band is None:
            raise RuntimeError(f"Missing band {band_index}")

        if selected_level == 0:
            bands.append(band)
        else:
            overview = band.GetOverview(selected_level - 1)
            if overview is None:
                raise RuntimeError(f"No overview {selected_level - 1} on band {band_index}")
            bands.append(overview)

    return bands

@deprecated("Replaced with jpeg generation due to performance")
def write_tile_png(stacked: np.ndarray, out_path: str, tile_w: int, tile_h: int, band_count: int) -> None:
    """
    Write tile to PNG file from stacked numpy array from gdal memory.
    """
    mem = gdal.GetDriverByName("MEM").Create("", tile_w, tile_h, band_count, gdal.GDT_Byte)
    for i in range(band_count):
        mem.GetRasterBand(i + 1).WriteArray(stacked[i])

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    gdal.Translate(out_path, mem, format="PNG")


def write_tile_jpeg(stacked: np.ndarray, out_path: str, quality: int = 85) -> None:
    """Creates JPEG tile from a stacked numpy array
    Supports 3 band RGB and 1 band greyscale

    Args:
        stacked (np.ndarray): array of shape (bands, height, width)
        out_path (str): absolute path to generate the image to
        quality (int): JPEG quality
    """
    if stacked.dtype != np.uint8:
        stacked = stacked.astype(np.uint8, copy=False)

    band_count, _, _ = stacked.shape

    if band_count == 1:
        image_array = stacked[0]
        image = Image.fromarray(image_array, mode="L")
    elif band_count == 3:
        image_array = np.moveaxis(stacked, 0, -1)
        image = Image.fromarray(image_array, mode="RGB")
    else:
        raise ValueError(f"JPEG output requires 1 or 3 bands, got {band_count}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    image.save(
        out_path,
        format="JPEG",
        quality=quality,
        optimize=False,
        subsampling="4:2:0",
    )