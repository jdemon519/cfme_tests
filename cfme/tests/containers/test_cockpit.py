import pytest

from cfme.containers.node import Node, NodeCollection
from cfme.containers.provider import ContainersProvider
from cfme.web_ui import toolbar as tb
from utils import testgen, version
from utils.appliance.implementations.ui import navigate_to


pytestmark = [
    pytest.mark.uncollectif(
        lambda provider: version.current_version() < "5.6"),
    pytest.mark.usefixtures('setup_provider'),
    pytest.mark.tier(1)]
pytest_generate_tests = testgen.generate(
    [ContainersProvider], scope='function')


@pytest.mark.polarion('CMP-10255')
def test_cockpit_button_access(provider, soft_assert):
    """ The test verifies the existence of cockpit "Web Console"
        button on each node

    """

    view = navigate_to(NodeCollection, 'All')

    names = [r.name.text for r in view.nodes]

    for name in names:
        obj = Node(name, provider)
        obj.load_details()
        soft_assert(
            tb.exists(
                'Open a new browser window with Cockpit for this '
                'VM.  This requires that Cockpit is pre-configured on the VM.'),
            'Cockpit "Web Console" button {} is not found on details page.'.format(name))