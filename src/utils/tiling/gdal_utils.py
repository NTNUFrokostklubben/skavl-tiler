import os

import numpy as np
from osgeo import gdal
from PIL import Image
from typing_extensions import deprecated


def inspect_source(source_path: str) -> tuple[int, int, int]:
    """Return (width_px, height_px, max_level) for a GeoTIFF at level 0."""
    ds = gdal.OpenEx(source_path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"GDAL open failed: {source_path}")
    try:
        width0 = int(ds.RasterXSize)
        height0 = int(ds.RasterYSize)
        band1 = ds.GetRasterBand(1)
        if band1 is None:
            raise RuntimeError("Dataset has no band 1")
        max_level = int(band1.GetOverviewCount())
        return width0, height0, max_level
    finally:
        ds = None


def read_tile_array(bands: list, tile_x: int, tile_y: int, tile_w: int, tile_h: int) -> np.ndarray:
    """Read tile pixel data from GDAL bands into a (bands, H, W) uint8 array."""
    x_offset = tile_x * tile_w
    y_offset = tile_y * tile_h

    level_w = int(bands[0].XSize)
    level_h = int(bands[0].YSize)

    read_w = max(0, min(tile_w, level_w - x_offset))
    read_h = max(0, min(tile_h, level_h - y_offset))
    if read_w == 0 or read_h == 0:
        raise RuntimeError("Tile window outside dataset bounds at this level")

    stacked = np.zeros((len(bands), tile_h, tile_w), dtype=np.uint8)
    for i, band in enumerate(bands):
        arr = band.ReadAsArray(x_offset, y_offset, read_w, read_h)
        if arr is None:
            raise RuntimeError("ReadAsArray returned None")
        stacked[i, :read_h, :read_w] = arr.astype(np.uint8, copy=False)

    return stacked


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