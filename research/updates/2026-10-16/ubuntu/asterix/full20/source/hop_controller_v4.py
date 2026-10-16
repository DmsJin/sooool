"""Keep the complete post-hop freshness guard, but retain diagonal horizontal motion."""
from hop_controller_v2 import RELEASE
from hop_controller_v3 import HopControllerV3


class HopControllerV4(HopControllerV3):
    def _landing_action(self, action):
        return RELEASE[action]
