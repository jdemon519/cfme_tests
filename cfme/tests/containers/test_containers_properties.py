# -*- coding: utf-8 -*-
import pytest
from cfme.containers.pod import Pod
from cfme.containers import pod
from cfme.containers.route import Route
from cfme.containers import route
from cfme.containers.project import Project
from cfme.containers import project
from utils import testgen
from utils.version import current_version


pytestmark = [
    pytest.mark.uncollectif(
        lambda: current_version() < "5.6"),
    pytest.mark.usefixtures('setup_provider'),
    pytest.mark.tier(1)]
pytest_generate_tests = testgen.generate(
    testgen.container_providers, scope="function")

# CMP-9911 # CMP-9877 # CMP-9867


@pytest.mark.parametrize('rel',
                         ['name',
                          'phase',
                          'creation_timestamp',
                          'resource_version',
                          'restart_policy',
                          'dns_policy',
                          'ip_address'
                          ])
def test_pods_properties_rel(provider, rel):
    """ This module verifies data integrity in the Properties table for:
        pods, routes and projects
    """
    for name in pod.get_all_pods():
        obj = Pod(name, provider)
        assert getattr(obj.summary.properties, rel).text_value


@pytest.mark.parametrize('rel',
                         ['name',
                          'creation_timestamp',
                          'resource_version',
                          'host_name'
                          ])
def test_routes_properties_rel(provider, rel):
    for name in route.get_all_routes():
        obj = Route(name, provider)
        assert getattr(obj.summary.properties, rel).text_value


@pytest.mark.parametrize('rel',
                         ['name',
                          'creation_timestamp',
                          'resource_version'
                          ])
def test_projects_properties_rel(provider, rel):
    for name in project.get_all_projects():
        obj = Project(name, provider)
        assert getattr(obj.summary.properties, rel).text_value
