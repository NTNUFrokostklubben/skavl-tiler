import hashlib
import os
from pathlib import Path

import grpc


from skavl_proto import tiler_pb2_grpc, tiler_pb2


def _canonicalize_path(p: str) -> str:
    return str(Path(p).expanduser().resolve())

def _make_source_id(canon_path: str) -> str:
    st = os.stat(canon_path)
    payload = f"{canon_path}|{st.st_size}|{int(st.st_mtime)}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()

class TilerServiceSericer(tiler_pb2_grpc.TilerServiceServicer):
    def __init__(self) -> None:
        self._sources: dict[str, str] = {}

    """
    Resolves a source path based on either a source_path in the proto message or a source_id.
    Returns a tuple of (source_id, canonical_source_path) which can be used by the other methods
    """
    def _resolve_source_path(self, source_ref: tiler_pb2.SourceRef, context) -> tuple[str, str]:
        active_ref_field = source_ref.WhichOneof("ref")
        if active_ref_field is None:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "SourceRef.ref is required")

        if active_ref_field == "source_path":
            canonical_source_path = _canonicalize_path(source_ref.source_path)
            if not os.path.exists(canonical_source_path):
                context.abort(grpc.StatusCode.NOT_FOUND, f"Source path not found: {canonical_source_path}")

            source_id = _make_source_id(canonical_source_path)
            self._sources[source_id] = canonical_source_path
            return source_id, canonical_source_path

        if active_ref_field == "source_id":
            source_id = source_ref.source_id
            canonical_source_path = self._sources.get(source_id)
            if canonical_source_path is None:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Unknown source_id: {source_id}")

            return source_id, canonical_source_path

        context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Unsupported SourceRef variant: {active_ref_field}")

    def DescribeSource(self, request, context):
        source_id, _source_path = self._resolve_source_path(request.source, context)

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
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "PlanViewport not implemented yet")