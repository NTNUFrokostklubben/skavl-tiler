from dataclasses import dataclass

from entity.tile.TileCoord import TileCoord


@dataclass(frozen=True)
class TileRef:
    """
    TileRef internal entity to mirror grpc interface
    """
    coord: TileCoord
    is_ready: bool
    local_path: str
    is_prefetch: bool
