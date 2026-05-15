from __future__ import annotations

import itertools
import os
from pathlib import Path

from entity.source.SourceDescriptor import SourceDescriptor
from entity.tile.TileCoord import TileCoord
from entity.tile.TileManifest import TileManifest
from entity.tile.TileRef import TileRef
from entity.viewport.ViewportRequest import ViewportRequest
from utils.tiling.gdal_utils import inspect_source
from utils.tiling.tile_generator import build_tile_path, try_generate_tile
from utils.tiling.viewport_planner import TileGridRange, plan_viewport_tiles, select_level


def _canonicalize_path(p: str) -> str:
    return str(Path(p).expanduser().resolve())


def _make_source_id(canonical_path: str) -> str:
    return Path(canonical_path).name


def _is_in_core(core_tiles: TileGridRange, tile_x: int, tile_y: int) -> bool:
    return (
        core_tiles.x.min_value <= tile_x <= core_tiles.x.max_value
        and core_tiles.y.min_value <= tile_y <= core_tiles.y.max_value
    )


class TilerService:
    """
    TilerService that handles all tiling

    Refactored out from gRPC tiler_servicer entrypoint
    """
    MAX_TILES_GENERATED_PER_CALL = 32

    def __init__(self, cache_root: Path, tile_w: int = 512, tile_h: int = 512) -> None:
        self._cache_root = cache_root
        self._tile_w = tile_w
        self._tile_h = tile_h
        self._source_id_to_path: dict[str, str] = {}
        self._source_id_to_descriptor: dict[str, SourceDescriptor] = {}

    def register_source(self, source_path: str) -> tuple[str, str]:
        """Register a source path and return (source_id, canonical_path)."""
        canonical_path = _canonicalize_path(source_path)
        if not os.path.exists(canonical_path):
            raise FileNotFoundError(f"Source path not found: {canonical_path}")
        source_id = _make_source_id(canonical_path)
        self._source_id_to_path[source_id] = canonical_path
        return source_id, canonical_path

    def resolve_source(self, source_id: str) -> tuple[str, str]:
        """Resolve a known source_id to (source_id, canonical_path)."""
        canonical_path = self._source_id_to_path.get(source_id)
        if canonical_path is None:
            raise KeyError(f"Unknown source_id: {source_id}")
        return source_id, canonical_path

    def describe_source(self, source_id: str, source_path: str) -> SourceDescriptor:
        """Inspect the GDAL source and cache its descriptor."""
        width0, height0, max_level = inspect_source(source_path)
        descriptor = SourceDescriptor(
            source_id=source_id,
            source_width_px=width0,
            source_height_px=height0,
            tile_width_px=self._tile_w,
            tile_height_px=self._tile_h,
            min_level=0,
            max_level=max_level,
        )
        self._source_id_to_descriptor[source_id] = descriptor
        return descriptor

    def plan_viewport(self, source_id: str, source_path: str, request: ViewportRequest) -> TileManifest:
        """Plan tiles required for a viewport, generating any missing ones up to the per-call cap."""
        descriptor = self._source_id_to_descriptor.get(source_id)
        if descriptor is None:
            raise RuntimeError(
                f"describe_source must be called before plan_viewport for source_id '{source_id}'"
            )

        selected_level = select_level(
            request.screen_pixels_per_source_pixel,
            max_level=descriptor.max_level,
        )

        plan = plan_viewport_tiles(
            viewport_x0=request.source_x0,
            viewport_y0=request.source_y0,
            viewport_width0=request.source_width0,
            viewport_height0=request.source_height0,
            source_width0=descriptor.source_width_px,
            source_height0=descriptor.source_height_px,
            selected_level=selected_level,
            tile_width=self._tile_w,
            tile_height=self._tile_h,
            prefetch_margin_tiles=request.prefetch_margin_tiles,
        )

        tiles = self._collect_tiles(source_id, source_path, plan, selected_level, request.queue_missing_tiles)
        return TileManifest(source_id=source_id, selected_level=selected_level, tiles=tiles)

    def _collect_tiles(
        self,
        source_id: str,
        source_path: str,
        plan,
        selected_level: int,
        queue_missing: bool,
    ) -> list[TileRef]:
        """
        Collects tiles and returns them as a list of Tile References
        """
        tile_refs: list[TileRef] = []
        generated = 0

        y_range = range(plan.requested_tiles.y.min_value, plan.requested_tiles.y.max_value + 1)
        x_range = range(plan.requested_tiles.x.min_value, plan.requested_tiles.x.max_value + 1)

        for tile_y, tile_x in itertools.product(y_range, x_range):
            tile_path = build_tile_path(self._cache_root, source_id, selected_level, tile_x, tile_y)
            is_in_core = _is_in_core(plan.core_tiles, tile_x, tile_y)

            if not os.path.exists(tile_path) and queue_missing and generated < self.MAX_TILES_GENERATED_PER_CALL:
                generated += try_generate_tile(
                    source_path, selected_level, tile_x, tile_y, tile_path, self._tile_w, self._tile_h
                )

            is_ready = os.path.exists(tile_path)
            tile_refs.append(TileRef(
                coord=TileCoord(level=selected_level, x=tile_x, y=tile_y),
                is_ready=is_ready,
                local_path=tile_path if is_ready else "",
                is_prefetch=not is_in_core,
            ))

        return tile_refs
