import pytest

from srt_mobile_api.live import live_enabled, run_live_smoke_from_env


pytestmark = pytest.mark.live


def test_read_only_live_smoke():
    if not live_enabled():
        pytest.skip("SRT live smoke requires explicit opt-in")
    result = run_live_smoke_from_env()
    assert result["loggedIn"] is True
    assert result["mutualVerificationLoaded"] is True
    assert result["personalTrainCount"] >= 0
    assert result["groupTrainCount"] >= 0
    assert result["selectorLoadedCount"] == 6
    assert "raw" not in result
    assert "text" not in repr(result).lower()
