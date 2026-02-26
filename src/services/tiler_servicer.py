import hashlib
import os
from pathlib import Path

import grpc

from skavl_proto import tiler_pb2_grpc, tiler_pb2
from utils.tiling.viewport_planner import select_level, plan_viewport_tiles


def _canonicalize_path(p: str) -> str:
    return str(Path(p).expanduser().resolve())


def _make_source_id(canon_path: str) -> str:
    st = os.stat(canon_path)
    payload = f"{canon_path}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


class TileServiceServicer(tiler_pb2_grpc.TilerServiceServicer):
    """gRPC servicer for TilerService."""

    def __init__(self) -> None:
        self._source_id_to_path: dict[str, str] = {}
        self._source_id_to_descriptor: dict[str, tuple[int, int, int]] = {}
        self._cache_root = r"C:\tilecache"
        self._tile_w = 512
        self._tile_h = 512

    def _resolve_source_path(self, source_ref: tiler_pb2.SourceRef, context) -> tuple[str, str]:
        """Resolve SourceRef to (source_id, canonical_source_path)."""

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

    def DescribeSource(self, request, context):
        source_id, _source_path = self._resolve_source_path(request.source, context)
        self._source_id_to_descriptor[source_id] = (1000, 1000, 4)

        # TODO: replace dummy values with GDAL dataset inspection
        return tiler_pb2.DescribeSourceResponse(
            descriptor=tiler_pb2.TilesetDescriptor(
                source_id=source_id,
                source_width_px=1000,
                source_height_px=1000,
                tile_width_px=512,
                tile_height_px=512,
                min_level=0,
                max_level=4,
            )
        )

    def PlanViewport(self, request, context):
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

        tile_refs: list[tiler_pb2.TileRef] = []

        req_x = plan.requested_tiles.x
        req_y = plan.requested_tiles.y
        core_x = plan.core_tiles.x
        core_y = plan.core_tiles.y

        for tile_y in range(req_y.min_value, req_y.max_value + 1):
            for tile_x in range(req_x.min_value, req_x.max_value + 1):
                in_core = (
                        core_x.min_value <= tile_x <= core_x.max_value
                        and core_y.min_value <= tile_y <= core_y.max_value
                )
                is_prefetch = not in_core

                tile_path = os.path.join(
                    self._cache_root, source_id, f"L{selected_level}", f"X{tile_x}", f"Y{tile_y}.png"
                )
                is_ready = os.path.exists(tile_path)

                tile_refs.append(
                    tiler_pb2.TileRef(
                        coord=tiler_pb2.TileCoord(level=selected_level, x=tile_x, y=tile_y),
                        state=(tiler_pb2.TILE_STATE_READY if is_ready else tiler_pb2.TILE_STATE_MISSING),
                        local_path=(tile_path if is_ready else ""),
                        is_prefetch=is_prefetch,
                    )
                )

        return tiler_pb2.PlanViewportResponse(
            manifest=tiler_pb2.ViewportTileManifest(
                source_id=source_id,
                selected_level=selected_level,
                tiles=tile_refs,
            )
        )