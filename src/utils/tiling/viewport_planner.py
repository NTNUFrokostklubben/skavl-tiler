from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple


@dataclass(frozen=True)
class Rect:
    """
    Axis-aligned rectangle in integer pixel coordinates.

    Fields:
      - x, y: top-left corner
      - width, height: non-negative extents
    """
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class IntRange:
    """
    Inclusive integer range [min_value, max_value].
    """
    min_value: int
    max_value: int


@dataclass(frozen=True)
class TileGridRange:
    """
    Inclusive tile index ranges for a 2D tile grid.
    """
    x: IntRange
    y: IntRange


@dataclass(frozen=True)
class ViewportPlan:
    """
    Planned tile ranges for rendering a viewport at a selected overview level.

    Fields:
      - selected_level: pyramid/overview level used for planning
      - core_tiles: tiles covering the viewport
      - requested_tiles: core_tiles expanded by a margin and clamped to bounds
    """
    selected_level: int
    core_tiles: TileGridRange
    requested_tiles: TileGridRange


def select_level(screen_pixels_per_source_pixel: float, max_level: int) -> int:
    """
    Select an integer pyramid/overview level from screen-to-source pixel scale.

    screen pixels per source pixel >= 1.0 => level 0
    screen pixels per source pixel < 1.0  => higher levels

    Args:
        screen_pixels_per_source_pixel (float): Calculated from client to determine what level to fetch

    Returns:
        quality level calculated from SSP
    """
    if max_level < 0:
        return 0

    if screen_pixels_per_source_pixel <= 0.0:
        return 0
    if screen_pixels_per_source_pixel >= 1.0:
        return 0

    ideal_level = int(round(math.log2(1.0 / screen_pixels_per_source_pixel)))
    if ideal_level < 0:
        return 0
    if ideal_level > max_level:
        return max_level
    return ideal_level


def plan_viewport_tiles(
        *,
        viewport_x0: int,
        viewport_y0: int,
        viewport_width0: int,
        viewport_height0: int,
        source_width0: int,
        source_height0: int,
        selected_level: int,
        tile_width: int,
        tile_height: int,
        prefetch_margin_tiles: int,
) -> ViewportPlan:
    """
    Compute tile ranges required to render a viewport.

    Coordinate spaces:
      - Inputs with suffix '0' are in level-0 (full resolution) source pixels.
      - Planning is performed on the selected_level grid with scale = 2^selected_level.

    Args:
        viewport_x0 (int): Source L0 x coordinate of viewport
        viewport_y0 (int): Source L0 y coordinate of viewport
        viewport_width0 (int): Source L0 pixel width of viewport
        viewport_height0 (int): Source L0 pixel height of viewport
        source_width0 (int): Source L0 pixel width of the GeoTIFF source image
        source_height0 (int): Source L0 pixel height of the GeoTIFF source image
        selected_level (int): Requested detail level where L0 is the highest resolution
        tile_width (int): Width per tile
        tile_height (int): Height per tile
        prefetch_margin_tiles (int): How many tiles outside of viewport should be fetched

    Returns:
        ViewportPlan
    """
    if tile_width <= 0 or tile_height <= 0:
        raise ValueError("tile_width and tile_height must be > 0")
    if source_width0 < 0 or source_height0 < 0:
        raise ValueError("source_width0 and source_height0 must be >= 0")
    if selected_level < 0:
        raise ValueError("selected_level must be >= 0")
    if prefetch_margin_tiles < 0:
        raise ValueError("prefetch_margin_tiles must be >= 0")

    input_viewport_level0 = Rect(viewport_x0, viewport_y0, viewport_width0, viewport_height0)
    source_bounds_level0 = Rect(0, 0, source_width0, source_height0)

    clamped_viewport_level0 = _clamp_rect_to_bounds(viewport_rect=input_viewport_level0, source_bounds=source_bounds_level0)
    viewport_on_level_grid = _project_rect_to_level_grid(rect_level0=clamped_viewport_level0, level=selected_level)

    scale = 1 << selected_level
    level_width_px = (source_width0 + scale - 1) // scale
    level_height_px = (source_height0 + scale - 1) // scale

    core_tiles, requested_tiles = _rect_pixels_to_tile_ranges(
        rect_px=viewport_on_level_grid,
        level_width_px=level_width_px,
        level_height_px=level_height_px,
        tile_width=tile_width,
        tile_height=tile_height,
        margin_tiles=prefetch_margin_tiles,
    )

    return ViewportPlan(selected_level=selected_level, core_tiles=core_tiles, requested_tiles=requested_tiles)


def _clamp_rect_to_bounds(*, viewport_rect: Rect, source_bounds: Rect) -> Rect:
    """
    Clamp a rectangle to an axis-aligned bounding rectangle.

    Output width/height are non-negative and the rectangle is fully contained in bounds.

    Args:
        viewport_rect (Rect): Viewport rectangle
        source_bounds (Rect): Source image rectangle

    Returns:
        Rect: Clamped Rect as bounds.

    """
    clamped_x = viewport_rect.x
    clamped_y = viewport_rect.y

    min_x = source_bounds.x
    min_y = source_bounds.y
    max_x = source_bounds.x + source_bounds.width
    max_y = source_bounds.y + source_bounds.height

    if clamped_x < min_x:
        clamped_x = min_x
    if clamped_y < min_y:
        clamped_y = min_y
    if clamped_x > max_x:
        clamped_x = max_x
    if clamped_y > max_y:
        clamped_y = max_y

    max_width_from_x = max_x - clamped_x
    max_height_from_y = max_y - clamped_y

    clamped_width = max(0, min(viewport_rect.width, max_width_from_x))
    clamped_height = max(0, min(viewport_rect.height, max_height_from_y))

    return Rect(clamped_x, clamped_y, clamped_width, clamped_height)


def _project_rect_to_level_grid(*, rect_level0: Rect, level: int) -> Rect:
    """
    Project level-0 pixel rectangle onto the pixel grid of a given level.

    Mapping:
      - scale = 2^level
      - x_level = floor(x0 / scale)
      - y_level = floor(y0 / scale)
      - width_level  = ceil(width0  / scale)
      - height_level = ceil(height0 / scale)

    Args:
        rect_level0 (Rect): Clamped viewport Rect at level zero from bounds
        level (int): Requested detail level where L0 is the highest resolution

    Returns:
        Rect: Scaled Rect based on requested level and bounds.

    """
    if level < 0:
        raise ValueError("level must be >= 0")

    scale = 1 << level

    x_level = rect_level0.x // scale
    y_level = rect_level0.y // scale
    width_level = (rect_level0.width + scale - 1) // scale
    height_level = (rect_level0.height + scale - 1) // scale

    return Rect(x_level, y_level, width_level, height_level)


def _rect_pixels_to_tile_ranges(
        *,
        rect_px: Rect,
        level_width_px: int,
        level_height_px: int,
        tile_width: int,
        tile_height: int,
        margin_tiles: int,
) -> Tuple[TileGridRange, TileGridRange]:
    """
    Convert pixel rectangle on a level grid into core and requested tile index ranges.

    Off-by-one rule:
      - Rectangle coverage uses last_pixel = (x + width - 1), (y + height - 1) when width/height > 0.

    Empty rectangle behavior:
      - width == 0 or height == 0 yields a degenerate 1-tile core range.

    Args:
        rect_px (Rect): Scaled Rect based on bounds and Level
        level_width_px (int): Scaled tile width based on level
        level_height_px (int): Scaled tile height based on level
        tile_width (int): Width per tile
        tile_height (int): Height per tile
        margin_tiles (int): Number of tiles to fetch outside of viewport range

    Returns:
        Tiles in core
        Tiles requested in total including prefetch tiles

    """
    if tile_width <= 0 or tile_height <= 0:
        raise ValueError("tile_width and tile_height must be > 0")
    if margin_tiles < 0:
        raise ValueError("margin_tiles must be >= 0")

    # // is integer division rounded down
    core_min_tile_x = rect_px.x // tile_width
    core_min_tile_y = rect_px.y // tile_height

    if rect_px.width <= 0 or rect_px.height <= 0:
        core_max_tile_x = core_min_tile_x
        core_max_tile_y = core_min_tile_y
    else:
        last_pixel_x = rect_px.x + rect_px.width - 1
        last_pixel_y = rect_px.y + rect_px.height - 1
        core_max_tile_x = last_pixel_x // tile_width
        core_max_tile_y = last_pixel_y // tile_height

    core_tiles = TileGridRange(
        x=IntRange(core_min_tile_x, core_max_tile_x),
        y=IntRange(core_min_tile_y, core_max_tile_y),
    )

    requested_min_tile_x = core_min_tile_x - margin_tiles
    requested_max_tile_x = core_max_tile_x + margin_tiles
    requested_min_tile_y = core_min_tile_y - margin_tiles
    requested_max_tile_y = core_max_tile_y + margin_tiles

    max_tile_x = max(0, (level_width_px - 1) // tile_width) if level_width_px > 0 else 0
    max_tile_y = max(0, (level_height_px - 1) // tile_height) if level_height_px > 0 else 0

    if requested_min_tile_x < 0:
        requested_min_tile_x = 0
    if requested_min_tile_y < 0:
        requested_min_tile_y = 0
    if requested_max_tile_x > max_tile_x:
        requested_max_tile_x = max_tile_x
    if requested_max_tile_y > max_tile_y:
        requested_max_tile_y = max_tile_y

    requested_tiles = TileGridRange(
        x=IntRange(requested_min_tile_x, requested_max_tile_x),
        y=IntRange(requested_min_tile_y, requested_max_tile_y),
    )

    return core_tiles, requested_tiles