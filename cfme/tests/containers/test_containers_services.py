# -*- coding: utf-8 -*-
import pytest
from cfme.containers.service import Service
from cfme.containers import service
from utils import testgen
from utils.version import current_version


pytestmark = [
    pytest.mark.uncollectif(
        lambda: current_version() < "5.6"),
    pytest.mark.usefixtures('setup_provider'),
    pytest.mark.tier(1)]
pytest_generate_tests = testgen.generate(
    testgen.container_providers, scope="function")

# CMP-9884


@pytest.mark.parametrize('rel',
                         ['name',
                          'creation_timestamp',
                          'resource_version',
                          'session_affinity',
                          'type',
                          'portal_ip'
                          ])
def test_services_properties_rel(provider, rel):
    """ This module verifies data integrity in the Properties table
        for services
    """
    for name in service.get_all_services():
        obj = Service(name, provider)
        assert getattr(obj.summary.properties, rel).text_value
