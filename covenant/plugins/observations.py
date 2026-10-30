# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional complete Monit-Docker and CertLord observation collectors."""
import sys

if sys.version_info >= (3, 8):
    from covenant.plugins.certlord import CovenantCertlordPlugin
    from covenant.classes.plugins import PLUGINS
    from covenant.services.observations import snapshot_metrics

    class CovenantMonitObservationPlugin(CovenantCertlordPlugin):
        PLUGIN_NAME = 'monit_observation'
        ACCEPT = 'application/json'
        UP_METRIC = 'covenant_monit_observation_up'
        SOURCE_KIND = 'monit'

        def _snapshot(self, text, collected_at, elapsed):
            return snapshot_metrics(text, self.SOURCE_KIND, collected_at, elapsed)

    class CovenantCertlordObservationPlugin(CovenantMonitObservationPlugin):
        PLUGIN_NAME = 'certlord_observation'
        UP_METRIC = 'covenant_certlord_observation_up'
        SOURCE_KIND = 'certlord'

    PLUGINS.register(CovenantMonitObservationPlugin)
    PLUGINS.register(CovenantCertlordObservationPlugin)
