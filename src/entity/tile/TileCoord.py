from dataclasses import dataclass


@dataclass(frozen=True)
class TileCoord:
    """
    TileCoord internal entity to mirror gRCP
    """
    level: int
    x: int
    y: int
