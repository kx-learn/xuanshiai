from app.core.config import Settings


def test_membership_price_override_uses_environment_value() -> None:
    configured = Settings(_env_file=None, membership_monthly_price=88.0)

    assert configured.membership_price_override("monthly", "price", 99.0) == 88.0
    assert configured.membership_price_override("quarterly", "price", 269.0) == 269.0


def test_point_cost_override_is_per_product() -> None:
    configured = Settings(_env_file=None, point_cost_extra_apply=20)

    assert configured.point_cost_override("extra_apply", 999) == 20
    assert configured.point_cost_override("paper_plane_unlock", 30) == 30
