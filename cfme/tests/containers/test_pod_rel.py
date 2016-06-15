#!/usr/bin/python
# -*- coding: utf-8 -*-
import pytest
from cfme.fixtures import pytest_selenium as sel
from cfme.containers import list_tbl as list_tbl_pods
from cfme.containers.pod import Pod
from utils import testgen
from utils.version import current_version
from cfme.web_ui import InfoBlock

pytestmark = [
    pytest.mark.uncollectif(
        lambda: current_version() < "5.5"),
    pytest.mark.usefixtures('setup_provider'),
    pytest.mark.tier(2)]
pytest_generate_tests = testgen.generate(
    testgen.container_providers, scope="function")


@pytest.mark.parametrize('rel',
                         ['Containers Provider',
                          'Project',
                          'Services',
                          'Replicator',
                          'Containers',
                          'Node'])
def test_pods_rel(provider, rel):
    sel.force_navigate('containers_pods')
    ui_pods = [r.name.text for r in list_tbl_pods.rows()]
    mgmt_objs = provider.mgmt.list_container_group()  # run only if table is not empty

    if ui_pods:
        # verify that mgmt pods exist in ui listed pods
        assert set(ui_pods).issubset(
            [obj.name for obj in mgmt_objs]), 'Missing objects'

    for name in ui_pods:
        obj = Pod(name, provider)

        val = obj.get_detail('Relationships', rel)
        if val == '0':
            continue
        obj.click_element('Relationships', rel)

        try:
            val = int(val)
            assert len([r for r in list_tbl_pods.rows()]) == val
        except ValueError:
            assert val == InfoBlock.text('Properties', 'Name')


def del_prov_rel(provider):
    provider.delete(cancel=False)
    provider.wait_for_delete()
