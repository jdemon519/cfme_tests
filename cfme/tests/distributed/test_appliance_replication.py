import pytest

import cfme.web_ui.flash as flash
from cfme.configure import configuration as conf
from cfme.infrastructure.provider import wait_for_a_provider
import cfme.fixtures.pytest_selenium as sel
from utils import testgen
from utils.appliance import provision_appliance
from utils.conf import cfme_data
from utils.wait import wait_for

pytest_generate_tests = testgen.generate(testgen.infra_providers, scope="module")


@pytest.mark.downstream
def test_appliance_replicate_between_regions(request, provider_crud):
    """Tests that a provider added to an appliance in one region
        is replicated to the parent appliance in another region.
    """
    appliance_data = cfme_data['appliance_provisioning']['single_appliance']
    appl1 = provision_appliance(appliance_data['version'], appliance_data['name'])
    appl2 = provision_appliance(appliance_data['version'], appliance_data['name'])

    def finalize():
        appl1.destroy()
        appl2.destroy()
    request.addfinalizer(finalize)
    appl1.configure(region=1, patch_ajax_wait=False)
    appl2.configure(region=2, patch_ajax_wait=False)
    with appl1.browser_session():
        conf.set_replication_worker_host(appl2.address)
        flash.assert_message_contain("Configuration settings saved for CFME Server")
        conf.set_server_role('database_synchronization')
        provider_crud.create()
        wait_for_a_provider()
        sel.force_navigate("cfg_diagnostics_region_replication")
        wait_for(lambda: conf.get_replication_status(navigate=False), fail_condition=None,
                 num_sec=120, delay=10, fail_func=sel.refresh)
        assert conf.get_replication_status()
        wait_for(lambda: conf.get_replication_backlog(navigate=False) == 0, fail_condition=None,
                 num_sec=120, delay=10, fail_func=sel.refresh)
    with appl2.browser_session():
        assert provider_crud.exists
