import os

import numpy as np
from osgeo import gdal


def extract_bands(data_source, selected_level: int) -> list:
    """
    Extract all bands from a GeoTIFF from provided source at defined level
    RGB by default.
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


def write_tile_png(stacked: np.ndarray, out_path: str, tile_w: int, tile_h: int, band_count: int) -> None:
    """
    Write tile to PNG file
    """
    mem = gdal.GetDriverByName("MEM").Create("", tile_w, tile_h, band_count, gdal.GDT_Byte)
    for i in range(band_count):
        mem.GetRasterBand(i + 1).WriteArray(stacked[i])

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    gdal.Translate(out_path, mem, format="PNG")