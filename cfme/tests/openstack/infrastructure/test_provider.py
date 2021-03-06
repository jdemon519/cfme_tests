"""Common tests for infrastructure provider"""

import pytest

from cfme.infrastructure.provider.openstack_infra import OpenstackInfraProvider
from cfme.web_ui import Quadicon
from utils import testgen
from utils.appliance.implementations.ui import navigate_to


pytest_generate_tests = testgen.generate([OpenstackInfraProvider],
                                         scope='module')
pytestmark = [pytest.mark.usefixtures("setup_provider_modscope")]


def test_api_port(provider):
    port = provider.get_yaml_data()['port']
    assert provider.summary.properties.api_port.value == port, 'Invalid API Port'


def test_credentials_quads(provider):
    navigate_to(provider, 'All')
    quad = Quadicon(provider.name, qtype='infra_prov')
    checked = str(quad.creds).split('-')[0]
    assert checked == 'checkmark'


def test_delete_provider(provider):
    provider.delete(cancel=False)
    navigate_to(provider, 'All')
    assert provider.name not in [q.name for q in Quadicon.all()]
