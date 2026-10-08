from datetime import timedelta

from src.application.use_cases.check_search_filter import CheckPolicy

POLICY = CheckPolicy(
    check_interval=timedelta(seconds=0),
    retry_base_delay=timedelta(seconds=60),
    retry_max_delay=timedelta(hours=1),
    max_advert_age=timedelta(hours=48),
    max_notifications_per_check=20,
    pause_after_missing_checks=3,
)
