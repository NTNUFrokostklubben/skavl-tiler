import hashlib
import itertools
import os
from pathlib import Path

import grpc
import numpy as np
from osgeo import gdal

from skavl_proto import tiler_pb2_grpc, tiler_pb2
from utils.tiling.gdal_utils import extract_bands, write_tile_png, write_tile_jpeg
from utils.tiling.viewport_planner import select_level, plan_viewport_tiles


def _canonicalize_path(p: str) -> str:
    """
    Expand user and resolve symlinks.
    Automatically regardless of system gets the total string with user dirs, etc. included.

    Args:
        p (str): Path string.
    """
    return str(Path(p).expanduser().resolve())


def _make_source_id(canonical_path: str) -> str:
    """Creates unique id based on file path, size, and mtime.
    Used primarily with generating unique id per loaded GeoTIFF

    Args:
        canonical_path (str): Canonical path to file

    Returns:
        Unique id
    """
    st = os.stat(canonical_path)
    payload = f"{canonical_path}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def _inspect_descriptor_gdal(source_path: str) -> tuple[int, int, int]:
    """Gets width, height, and max level from a GeoTIFF datasource.
    Used mainly for planning and pre-populating other services

    Args:
        source_path (str): Path to GeoTIFF

    """
    ds = gdal.OpenEx(source_path, gdal.GA_ReadOnly)
    if ds is None:
        raise RuntimeError(f"GDAL open failed: {source_path}")

    try:
        width0 = int(ds.RasterXSize)
        height0 = int(ds.RasterYSize)

        band1 = ds.GetRasterBand(1)
        if band1 is None:
            raise RuntimeError("Dataset has no band 1")

        overview_count = int(band1.GetOverviewCount())
        max_level = overview_count  # level 1..N maps to overview index 0..N-1
        return width0, height0, max_level
    finally:
        ds = None  # close dataset handle


class TileServiceServicer(tiler_pb2_grpc.TilerServiceServicer):
    """gRPC servicer for TilerService.

    """
    _MAX_TILES_GENERATED_PER_CALL = 32

    def __init__(self) -> None:
        self._source_id_to_path: dict[str, str] = {}
        self._source_id_to_descriptor: dict[str, tuple[int, int, int]] = {}
        self._cache_root = r"C:\tilecache"
        self._tile_w = 512
        self._tile_h = 512

    def DescribeSource(self, request, context):
        """Returns metadata for an image used for calculation for the tile plan.

        Args:
            request: DescribeSourceRequest
            context: grpc.ServicerContext

        Return:
            DescribeSourceResponse
        """
        source_id, source_path = self._resolve_source_path(request.source, context)

        try:
            width0, height0, max_level = _inspect_descriptor_gdal(source_path)
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"DescribeSource GDAL inspection failed: {e}")

        self._source_id_to_descriptor[source_id] = (width0, height0, max_level)

        return tiler_pb2.DescribeSourceResponse(
            descriptor=tiler_pb2.TilesetDescriptor(
                source_id=source_id,
                source_width_px=width0,
                source_height_px=height0,
                tile_width_px=self._tile_w,
                tile_height_px=self._tile_h,
                min_level=0,
                max_level=max_level,
            )
        )

    def PlanViewport(self, request, context):
        """Tile plan based on viewport passed from SKAVL

        Args:
            request: tiler_pb2.PlanView
            context: grpc context

        Return:
            tiler_pb2.TilePlan

        """
        source_id, _canonical_source_path = self._resolve_source_path(request.source, context)

        descriptor = self._source_id_to_descriptor.get(source_id)
        if descriptor is None:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION,
                          "DescribeSource must be called before PlanViewport for this source_id")

        source_width0, source_height0, max_level = descriptor

        selected_level = select_level(
            request.screen_pixels_per_source_pixel,
            max_level=max_level,
        )

        plan = plan_viewport_tiles(
            viewport_x0=int(request.viewport_source_rect_px.x),
            viewport_y0=int(request.viewport_source_rect_px.y),
            viewport_width0=int(request.viewport_source_rect_px.width),
            viewport_height0=int(request.viewport_source_rect_px.height),
            source_width0=source_width0,
            source_height0=source_height0,
            selected_level=selected_level,
            tile_width=self._tile_w,
            tile_height=self._tile_h,
            prefetch_margin_tiles=int(request.prefetch_margin_tiles),
        )

        tile_refs = self._plan_to_tile_refs(_canonical_source_path, plan, request, selected_level, source_id)

        return tiler_pb2.PlanViewportResponse(
            manifest=tiler_pb2.ViewportTileManifest(
                source_id=source_id,
                selected_level=selected_level,
                tiles=tile_refs,
            )
        )

    def _read_tile_into_array(self, bands: list, tile_x: int, tile_y: int) -> np.ndarray:
        """
        Read tiles from the given bands at the given tile coordinates.

        Args:
            bands (list): List of bands from GDAL dataset.
            tile_x (int): X coordinate of the tile.
            tile_y (int): Y coordinate of the tile.

        Return:
            3D numpy array of shape (bands, height, width)

        """
        x_offset = tile_x * self._tile_w
        y_offset = tile_y * self._tile_h

        level_w = int(bands[0].XSize)
        level_h = int(bands[0].YSize)

        read_w = max(0, min(self._tile_w, level_w - x_offset))
        read_h = max(0, min(self._tile_h, level_h - y_offset))
        if read_w == 0 or read_h == 0:
            raise RuntimeError("Tile window outside dataset bounds at this level")

        # Creates an n-dimensional array for each pixel location (h,w) per band.
        stacked = np.zeros((len(bands), self._tile_h, self._tile_w), dtype=np.uint8)
        for i, band in enumerate(bands):
            arr = band.ReadAsArray(x_offset, y_offset, read_w, read_h)
            if arr is None:
                raise RuntimeError("ReadAsArray returned None")
            stacked[i, :read_h, :read_w] = arr.astype(np.uint8, copy=False)

        return stacked

    def _plan_to_tile_refs(self, canonical_source_path, plan, request, selected_level, source_id):
        """
        Maps a tile plan to tile references.

        Calculates which tiles are "in the core" of the viewport provided. If tile is not in code, it will not be
        appended/created as it is not needed for the current viewport.

        Args:
            canonical_source_path: The canonical path to the source dataset.
            plan: Tile plan
            request: Tile request
            selected_level: Quality level, L0 is the best quality whilst higher levels are lower quality.
            source_id: Image source id reference

        Return:
            list[tiler_pb2.TileRef]

        """

        tile_refs: list[tiler_pb2.TileRef] = []
        generated_this_call = 0

        y_range = range(plan.requested_tiles.y.min_value, plan.requested_tiles.y.max_value + 1)
        x_range = range(plan.requested_tiles.x.min_value, plan.requested_tiles.x.max_value + 1)

        for tile_y, tile_x in itertools.product(y_range, x_range):
            tile_path = self._build_tile_path(source_id, selected_level, tile_x, tile_y)
            is_in_core = self._is_in_core(plan.core_tiles, tile_x, tile_y)

            if not os.path.exists(
                    tile_path) and request.queue_missing_tiles and generated_this_call < self._MAX_TILES_GENERATED_PER_CALL:
                generated_this_call += self._try_generate_tile(canonical_source_path, selected_level, tile_x, tile_y,
                                                               tile_path)

            tile_refs.append(self._build_tile_ref(selected_level, tile_x, tile_y, tile_path, is_in_core))

        return tile_refs

    @staticmethod
    def _build_tile_ref(selected_level: int, tile_x: int, tile_y: int, tile_path: str,
                        is_in_core: bool) -> tiler_pb2.TileRef:
        """
        Build a TileRef message for a given tile coordinate

        Args:
            selected_level (int): Quality level, L0 is the best quality whilst higher levels are lower quality.
            tile_x (int): X coordinate of the tile.
            tile_y (int): Y coordinate of the tile.
            tile_path (str): Global path for the tile
            is_in_core (bool): if tile is in the "core region" or prefetch region

        Return:
            tiler_pb2.TileRef: Tile
        """
        is_ready = os.path.exists(tile_path)
        return tiler_pb2.TileRef(
            coord=tiler_pb2.TileCoord(level=selected_level, x=tile_x, y=tile_y),
            state=tiler_pb2.TILE_STATE_READY if is_ready else tiler_pb2.TILE_STATE_MISSING,
            local_path=tile_path if is_ready else "",
            is_prefetch=not is_in_core,
        )

    @staticmethod
    def _is_in_core(core_tiles, tile_x: int, tile_y: int) -> bool:
        """
        Determines if tile is "in the core", as in if it should be rendered or not.

        Args:
            core_tiles: list of core tiles
            tile_x (int): X coordinate of the tile.
            tile_y (int): Y coordinate of the tile.

        Return:
            bool: True if tile is in core, False otherwise.
        """
        return (
                core_tiles.x.min_value <= tile_x <= core_tiles.x.max_value
                and core_tiles.y.min_value <= tile_y <= core_tiles.y.max_value
        )

    def _build_tile_path(self, source_id: str, selected_level: int, tile_x: int, tile_y: int) -> str:
        """
        Constructs file path based on level and coordinate.

        Args:
            source_id (str): id for the image source
            selected_level (int): Quality level, L0 is the best quality whilst higher levels are lower quality.
            tile_x (int): X coordinate of the tile.
            tile_y (int): Y coordinate of the tile.

        Return:
            str: Path to tile.

        """
        return os.path.join(self._cache_root, source_id, f"L{selected_level}", f"X{tile_x}", f"Y{tile_y}.jpg")

    def _try_generate_tile(self, canonical_source_path: str, selected_level: int, tile_x: int, tile_y: int,
                           tile_path: str) -> int:
        """
        Attempts to generate a tile PNG. Returns 1 if successful, 0 otherwise.

        Args:
            canonical_source_path: Path to the source image.
            selected_level (int): Quality level, L0 is the best quality whilst higher levels are lower quality.
            tile_x (int): X coordinate of the tile.
            tile_y (int): Y coordinate of the tile.
            tile_path (str): Built path to tile.

        """
        try:
            self._generate_tile_png(
                source_path=canonical_source_path,
                selected_level=selected_level,
                tile_x=tile_x,
                tile_y=tile_y,
                out_path=tile_path,
            )
            return 1
        except Exception:
            return 0

    def _generate_tile_png(
            self,
            source_path: str,
            selected_level: int,
            tile_x: int,
            tile_y: int,
            out_path: str,
    ) -> None:
        """
        Generates a PNG tile from the source at the given level and coordinates.

        Args:
            source_path (str): Path to the source image
            selected_level (int): Quality level, L0 is the best quality whilst higher levels are lower quality.
            tile_x (int): X coordinate of the tile.
            tile_y (int): Y coordinate of the tile.
            out_path (str): Built path to tile.
        """
        data_source = gdal.OpenEx(source_path, gdal.GA_ReadOnly)
        if data_source is None:
            raise RuntimeError(f"GDAL open failed: {source_path}")

        try:
            bands = extract_bands(data_source, selected_level)
            stacked = self._read_tile_into_array(bands, tile_x, tile_y)
            write_tile_jpeg(stacked, out_path, quality=100)
        finally:
            data_source = None

    def _resolve_source_path(self, source_ref: tiler_pb2.SourceRef, context) -> tuple[str, str]:
        """Resolve SourceRef to (source_id, canonical_source_path).

        Args:
            source_ref (tiler_pb2.SourceRef): Source reference
            context: gRPC context

        """

        active_ref_field = source_ref.WhichOneof("ref")
        if active_ref_field is None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "SourceRef.ref is required")

        if active_ref_field == "source_path":
            canonical_source_path = _canonicalize_path(source_ref.source_path)
            if not os.path.exists(canonical_source_path):
                context.abort(grpc.StatusCode.NOT_FOUND, f"Source path not found: {canonical_source_path}")

            source_id = _make_source_id(canonical_source_path)
            self._source_id_to_path[source_id] = canonical_source_path
            return source_id, canonical_source_path

        if active_ref_field == "source_id":
            source_id = source_ref.source_id
            canonical_source_path = self._source_id_to_path.get(source_id)
            if canonical_source_path is None:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Unknown source_id: {source_id}")

            return source_id, canonical_source_path

        context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Unsupported SourceRef variant: {active_ref_field}")
