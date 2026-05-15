from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDescriptor:
    """
    SourceDescriptor internal entity to mirror gRPC
    """
    source_id: str
    source_width_px: int
    source_height_px: int
    tile_width_px: int
    tile_height_px: int
    min_level: int
    max_level: int
