import os
from pathlib import Path

from osgeo import gdal

from utils.tiling.gdal_utils import extract_bands, read_tile_array, write_tile_jpeg


def build_tile_path(cache_root: Path, source_id: str, level: int, tile_x: int, tile_y: int) -> str:
    return os.path.join(cache_root, source_id, f"L{level}", f"X{tile_x}", f"Y{tile_y}.jpg")


def generate_tile(
    source_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
    out_path: str,
    tile_w: int,
    tile_h: int,
) -> None:
    """Generate a JPEG tile from a GeoTIFF source at the given level and coordinates."""
    data_source = gdal.OpenEx(source_path, gdal.GA_ReadOnly)
    if data_source is None:
        raise RuntimeError(f"GDAL open failed: {source_path}")
    try:
        bands = extract_bands(data_source, level)
        stacked = read_tile_array(bands, tile_x, tile_y, tile_w, tile_h)
        write_tile_jpeg(stacked, out_path, quality=100)
    finally:
        data_source = None


def try_generate_tile(
    source_path: str,
    level: int,
    tile_x: int,
    tile_y: int,
    out_path: str,
    tile_w: int,
    tile_h: int,
) -> int:
    """Attempt tile generation. Returns 1 on success, 0 on failure."""
    try:
        generate_tile(source_path, level, tile_x, tile_y, out_path, tile_w, tile_h)
        return 1
    except Exception:
        return 0
