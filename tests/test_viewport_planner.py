from utils.tiling.viewport_planner import plan_viewport_tiles, select_level


def test_select_level_zoom_in_is_level0():
    assert select_level(1.0, max_level=6) == 0
    assert select_level(2.0, max_level=6) == 0


def test_select_level_zoom_out_scales_up():
    assert select_level(0.5, max_level=6) == 1
    assert select_level(0.25, max_level=6) == 2


def test_tile_range_single_tile_at_origin():

    plan = plan_viewport_tiles(
        viewport_x0=0,
        viewport_y0=0,
        viewport_width0=512,
        viewport_height0=512,
        source_width0=2048,
        source_height0=2048,
        selected_level=0,
        tile_width=512,
        tile_height=512,
        prefetch_margin_tiles=0,
    )
    assert plan.core_tiles.x.min_value == 0
    assert plan.core_tiles.x.max_value == 0
    assert plan.core_tiles.y.min_value == 0
    assert plan.core_tiles.y.max_value == 0


def test_tile_range_crosses_boundary_by_one_pixel():
    plan = plan_viewport_tiles(
        viewport_x0=0,
        viewport_y0=0,
        viewport_width0=513,
        viewport_height0=512,
        source_width0=2048,
        source_height0=2048,
        selected_level=0,
        tile_width=512,
        tile_height=512,
        prefetch_margin_tiles=0,
    )
    assert plan.core_tiles.x.min_value == 0
    assert plan.core_tiles.x.max_value == 1  # crosses into next tile
    assert plan.core_tiles.y.min_value == 0
    assert plan.core_tiles.y.max_value == 0


def test_prefetch_margin_expands_and_clamps_at_edges():
    plan = plan_viewport_tiles(
        viewport_x0=0,
        viewport_y0=0,
        viewport_width0=512,
        viewport_height0=512,
        source_width0=1024,
        source_height0=1024,
        selected_level=0,
        tile_width=512,
        tile_height=512,
        prefetch_margin_tiles=2,
    )
    # Source is 2x2 tiles. Expanded range must clamp to [0..1].
    assert plan.requested_tiles.x.min_value == 0
    assert plan.requested_tiles.x.max_value == 1
    assert plan.requested_tiles.y.min_value == 0
    assert plan.requested_tiles.y.max_value == 1


def test_level_scaling_reduces_tile_coverage():
    plan0 = plan_viewport_tiles(
        viewport_x0=0, viewport_y0=0, viewport_width0=1024, viewport_height0=1024,
        source_width0=4096, source_height0=4096,
        selected_level=0, tile_width=512, tile_height=512, prefetch_margin_tiles=0,
    )
    assert (plan0.core_tiles.x.min_value, plan0.core_tiles.x.max_value) == (0, 1)
    assert (plan0.core_tiles.y.min_value, plan0.core_tiles.y.max_value) == (0, 1)

    plan1 = plan_viewport_tiles(
        viewport_x0=0, viewport_y0=0, viewport_width0=1024, viewport_height0=1024,
        source_width0=4096, source_height0=4096,
        selected_level=1, tile_width=512, tile_height=512, prefetch_margin_tiles=0,
    )
    assert (plan1.core_tiles.x.min_value, plan1.core_tiles.x.max_value) == (0, 0)
    assert (plan1.core_tiles.y.min_value, plan1.core_tiles.y.max_value) == (0, 0)


def test_viewport_is_clamped_to_source_bounds():
    plan = plan_viewport_tiles(
        viewport_x0=-100,
        viewport_y0=-200,
        viewport_width0=600,
        viewport_height0=700,
        source_width0=512,
        source_height0=512,
        selected_level=0,
        tile_width=512,
        tile_height=512,
        prefetch_margin_tiles=0,
    )
    # Clamped to a 512x512 image -> must be tile (0,0)
    assert plan.core_tiles.x.min_value == 0
    assert plan.core_tiles.x.max_value == 0
    assert plan.core_tiles.y.min_value == 0
    assert plan.core_tiles.y.max_value == 0