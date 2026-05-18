from dataclasses import dataclass


@dataclass(frozen=True)
class ViewportRequest:
    """
    ViewportRequest internal entity to mirror gRPC
    """
    source_x0: int
    source_y0: int
    source_width0: int
    source_height0: int
    screen_pixels_per_source_pixel: float
    prefetch_margin_tiles: int
    queue_missing_tiles: bool
