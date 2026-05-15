from __future__ import annotations

from dataclasses import dataclass, field

from entity.tile.TileRef import TileRef


@dataclass(frozen=True)
class TileManifest:
    """
    TileManifest internal entity to mirror gRPC
    """
    source_id: str
    selected_level: int
    tiles: list[TileRef] = field(default_factory=list)
