import grpc

from skavl_proto import tiler_pb2_grpc, tiler_pb2

from entity.tile.TileRef import TileRef
from entity.viewport.ViewportRequest import ViewportRequest
from services.tiler_servicer.TilerService import TilerService


def _tile_ref_to_proto(ref: TileRef) -> tiler_pb2.TileRef:
    return tiler_pb2.TileRef(
        coord=tiler_pb2.TileCoord(level=ref.coord.level, x=ref.coord.x, y=ref.coord.y),
        state=tiler_pb2.TILE_STATE_READY if ref.is_ready else tiler_pb2.TILE_STATE_MISSING,
        local_path=ref.local_path,
        is_prefetch=ref.is_prefetch,
    )


class TileServiceServicer(tiler_pb2_grpc.TilerServiceServicer):
    def __init__(self, tiler: TilerService) -> None:
        self._tiler = tiler

    def DescribeSource(self, request, context):
        source_id, source_path = self._resolve_source_ref(request.source, context)

        try:
            descriptor = self._tiler.describe_source(source_id, source_path)
        except Exception as e:
            context.abort(grpc.StatusCode.INTERNAL, f"DescribeSource failed: {e}")

        return tiler_pb2.DescribeSourceResponse(
            descriptor=tiler_pb2.TilesetDescriptor(
                source_id=descriptor.source_id,
                source_width_px=descriptor.source_width_px,
                source_height_px=descriptor.source_height_px,
                tile_width_px=descriptor.tile_width_px,
                tile_height_px=descriptor.tile_height_px,
                min_level=descriptor.min_level,
                max_level=descriptor.max_level,
            )
        )

    def PlanViewport(self, request, context):
        source_id, source_path = self._resolve_source_ref(request.source, context)

        viewport_request = ViewportRequest(
            source_x0=int(request.viewport_source_rect_px.x),
            source_y0=int(request.viewport_source_rect_px.y),
            source_width0=int(request.viewport_source_rect_px.width),
            source_height0=int(request.viewport_source_rect_px.height),
            screen_pixels_per_source_pixel=request.screen_pixels_per_source_pixel,
            prefetch_margin_tiles=int(request.prefetch_margin_tiles),
            queue_missing_tiles=request.queue_missing_tiles,
        )

        try:
            manifest = self._tiler.plan_viewport(source_id, source_path, viewport_request)
        except RuntimeError as e:
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(e))

        return tiler_pb2.PlanViewportResponse(
            manifest=tiler_pb2.ViewportTileManifest(
                source_id=manifest.source_id,
                selected_level=manifest.selected_level,
                tiles=[_tile_ref_to_proto(t) for t in manifest.tiles],
            )
        )

    def _resolve_source_ref(self, source_ref, context) -> tuple[str, str]:
        active = source_ref.WhichOneof("ref")
        if active is None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "SourceRef.ref is required")

        if active == "source_path":
            try:
                return self._tiler.register_source(source_ref.source_path)
            except FileNotFoundError as e:
                context.abort(grpc.StatusCode.NOT_FOUND, str(e))

        if active == "source_id":
            try:
                return self._tiler.resolve_source(source_ref.source_id)
            except KeyError as e:
                context.abort(grpc.StatusCode.NOT_FOUND, str(e))

        context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Unsupported SourceRef variant: {active}")
