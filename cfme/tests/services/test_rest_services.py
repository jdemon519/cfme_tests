# -*- coding: utf-8 -*-
import datetime
import fauxfactory
import pytest

from cfme.rest.gen_data import dialog as _dialog
from cfme.rest.gen_data import services as _services
from cfme.rest.gen_data import service_data as _service_data
from cfme.rest.gen_data import service_catalogs as _service_catalogs
from cfme.rest.gen_data import service_templates as _service_templates
from cfme.rest.gen_data import orchestration_templates as _orchestration_templates
from cfme.rest.gen_data import blueprints as _blueprints
from cfme import test_requirements
from cfme.infrastructure.provider import InfraProvider
from fixtures.provider import setup_one_or_skip
from utils import error, version
from utils.providers import ProviderFilter
from utils.wait import wait_for
from utils.blockers import BZ


pytestmark = [
    pytest.mark.long_running,
    test_requirements.service,
    pytest.mark.tier(2)
]


@pytest.fixture(scope="module")
def a_provider(request):
    pf = ProviderFilter(classes=[InfraProvider], required_fields=[
        ['provisioning', 'template'],
        ['provisioning', 'host'],
        ['provisioning', 'datastore'],
        ['provisioning', 'vlan'],
        ['provisioning', 'catalog_item_type']])
    return setup_one_or_skip(request, filters=[pf])


def wait_for_vm_power_state(vm, resulting_state):
    wait_for(
        lambda: vm.power_state == resulting_state,
        num_sec=600, delay=20, fail_func=vm.reload,
        message='Wait for VM to {} (current state: {})'.format(
            resulting_state, vm.power_state))


def vm_retired(vm):
    vm.reload()
    try:
        if vm.retirement_state == 'retired':
            return True
    except AttributeError:
        pass
    return False


def service_body(**kwargs):
    uid = fauxfactory.gen_alphanumeric(5)
    body = {
        'name': 'test_rest_service_{}'.format(uid),
        'description': 'Test REST Service {}'.format(uid),
    }
    body.update(kwargs)
    return body


@pytest.fixture(scope="function")
def dialog():
    return _dialog()


@pytest.fixture(scope="function")
def service_catalogs(request, rest_api):
    response = _service_catalogs(request, rest_api)
    assert rest_api.response.status_code == 200
    return response


@pytest.fixture(scope="function")
def services(request, rest_api, a_provider):
    if version.current_version() >= '5.7':
        # create simple service using REST API
        bodies = [service_body() for _ in range(3)]
        collection = rest_api.collections.services
        new_services = collection.action.create(*bodies)
        assert rest_api.response.status_code == 200

        @request.addfinalizer
        def _finished():
            collection.reload()
            ids = [service.id for service in new_services]
            delete_entities = [service for service in collection if service.id in ids]
            if len(delete_entities) != 0:
                collection.action.delete(*delete_entities)

        return new_services
    else:
        # create full-blown service using UI
        s_dialog = _dialog()
        s_catalogs = _service_catalogs(request, rest_api)
        return _services(request, rest_api, a_provider, s_dialog, s_catalogs)


@pytest.fixture(scope="function")
def service_templates(request, rest_api, dialog):
    response = _service_templates(request, rest_api, dialog)
    assert rest_api.response.status_code == 200
    return response


@pytest.fixture(scope="function")
def service_data(request, rest_api, a_provider, dialog, service_catalogs):
    return _service_data(request, rest_api, a_provider, dialog, service_catalogs)


class TestServiceRESTAPI(object):
    def test_edit_service(self, rest_api, services):
        """Tests editing a service.
        Prerequisities:
            * An appliance with ``/api`` available.
        Steps:
            * POST /api/services (method ``edit``) with the ``name``
            * Check if the service with ``new_name`` exists
        Metadata:
            test_flag: rest
        """
        for service in services:
            new_name = fauxfactory.gen_alphanumeric()
            response = service.action.edit(name=new_name)
            assert rest_api.response.status_code == 200
            assert response.name == new_name
            service.reload()
            assert service.name == new_name

    def test_edit_multiple_services(self, rest_api, services):
        """Tests editing multiple services at a time.
        Prerequisities:
            * An appliance with ``/api`` available.
        Steps:
            * POST /api/services (method ``edit``) with the list of dictionaries used to edit
            * Check if the services with ``new_name`` each exists
        Metadata:
            test_flag: rest
        """
        new_names = []
        services_data_edited = []
        for service in services:
            new_name = fauxfactory.gen_alphanumeric()
            new_names.append(new_name)
            services_data_edited.append({
                "href": service.href,
                "name": new_name,
            })
        response = rest_api.collections.services.action.edit(*services_data_edited)
        assert rest_api.response.status_code == 200
        for i, resource in enumerate(response):
            assert resource.name == new_names[i]
            service = services[i]
            service.reload()
            assert service.name == new_names[i]

    # POST method is not available on < 5.8, as described in BZ 1414852
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.8')
    def test_delete_service_post(self, rest_api, services):
        """Tests deleting services from detail using POST method.

        Metadata:
            test_flag: rest
        """
        for service in services:
            service.action.delete(force_method="post")
            assert rest_api.response.status_code == 200
            with error.expected("ActiveRecord::RecordNotFound"):
                service.action.delete(force_method="post")
            assert rest_api.response.status_code == 404

    def test_delete_service_delete(self, rest_api, services):
        """Tests deleting services from detail using DELETE method.

        Metadata:
            test_flag: rest
        """
        for service in services:
            service.action.delete(force_method="delete")
            assert rest_api.response.status_code == 204
            with error.expected("ActiveRecord::RecordNotFound"):
                service.action.delete(force_method="delete")
            assert rest_api.response.status_code == 404

    def test_delete_services(self, rest_api, services):
        """Tests deleting services from collection.

        Metadata:
            test_flag: rest
        """
        rest_api.collections.services.action.delete(*services)
        assert rest_api.response.status_code == 200
        with error.expected("ActiveRecord::RecordNotFound"):
            rest_api.collections.services.action.delete(*services)
        assert rest_api.response.status_code == 404

    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_retire_service_now(self, rest_api, service_data, from_detail):
        """Test retiring a service now.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        service = collection.get(name=service_data['service_name'])
        vm = rest_api.collections.vms.get(name=service_data['vm_name'])

        if from_detail:
            service.action.retire()
            assert rest_api.response.status_code == 200
        else:
            collection.action.retire(service)
            assert rest_api.response.status_code == 200

        wait_for(
            lambda: not collection.find_by(name=service.name),
            num_sec=600,
            delay=10,
        )
        wait_for(lambda: vm_retired(vm), num_sec=1000, delay=10)

    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_retire_service_future(self, rest_api, services, from_detail):
        """Test retiring a service in future.

        Metadata:
            test_flag: rest
        """
        date = (datetime.datetime.now() + datetime.timedelta(days=5)).strftime("%Y/%m/%d")
        future = {
            "date": date,
            "warn": "4",
        }

        if from_detail:
            for service in services:
                service.action.retire(**future)
                assert rest_api.response.status_code == 200
        else:
            rest_api.collections.services.action.retire(*services, **future)
            assert rest_api.response.status_code == 200

        def _finished(service):
            service.reload()
            return hasattr(service, "retires_on") and hasattr(service, "retirement_warn")

        for service in services:
            wait_for(
                lambda: _finished(service),
                num_sec=60,
                delay=5
            )

    def test_set_service_owner(self, rest_api, services):
        """Tests set_ownership action on /api/services/:id.

        Metadata:
            test_flag: rest
        """
        user = rest_api.collections.users.get(userid="admin")
        data = {
            "owner": {"href": user.href}
        }
        for service in services:
            service.action.set_ownership(**data)
            assert rest_api.response.status_code == 200
            service.reload()
            assert hasattr(service, "evm_owner_id")
            assert service.evm_owner_id == user.id

    def test_set_services_owner(self, rest_api, services):
        """Tests set_ownership action on /api/services collection.

        Metadata:
            test_flag: rest
        """
        user = rest_api.collections.users.get(userid="admin")
        requests = [{
            "href": service.href,
            "owner": {"href": user.href}
        } for service in services]
        rest_api.collections.services.action.set_ownership(*requests)
        assert rest_api.response.status_code == 200
        for service in services:
            service.reload()
            assert hasattr(service, "evm_owner_id")
            assert service.evm_owner_id == user.id

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_power_service(self, rest_api, service_data, from_detail):
        """Tests power operations on /api/services and /api/services/:id.

        * start, stop and suspend actions
        * transition from one power state to another

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        service = collection.get(name=service_data['service_name'])
        vm = rest_api.collections.vms.get(name=service_data['vm_name'])

        def _action_and_check(action, resulting_state):
            if from_detail:
                getattr(service.action, action)()
            else:
                getattr(collection.action, action)(service)
            assert rest_api.response.status_code == 200
            wait_for_vm_power_state(vm, resulting_state)

        wait_for_vm_power_state(vm, 'on')
        _action_and_check('stop', 'off')
        _action_and_check('start', 'on')
        _action_and_check('suspend', 'suspended')
        _action_and_check('start', 'on')

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.meta(blockers=[BZ(1416146, forced_streams=['5.7', '5.8', 'upstream'])])
    def test_create_service_from_parent(self, request, rest_api):
        """Tests creation of new service that reference existing service.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        service = collection.action.create(service_body())[0]
        request.addfinalizer(service.action.delete)
        bodies = []
        for ref in {'id': service.id}, {'href': service.href}:
            bodies.append(service_body(parent_service=ref))
        response = collection.action.create(*bodies)
        assert rest_api.response.status_code == 200
        for ent in response:
            assert ent.ancestry == str(service.id)

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_delete_parent_service(self, rest_api):
        """Tests that when parent service is deleted, child service is deleted automatically.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        grandparent = collection.action.create(service_body())[0]
        parent = collection.action.create(service_body(parent_service={'id': grandparent.id}))[0]
        child = collection.action.create(service_body(parent_service={'id': parent.id}))[0]
        assert parent.ancestry == str(grandparent.id)
        assert child.ancestry == '{}/{}'.format(grandparent.id, parent.id)
        grandparent.action.delete()
        assert rest_api.response.status_code in (200, 204)
        wait_for(
            lambda: not rest_api.collections.services.find_by(name=grandparent.name),
            num_sec=600,
            delay=10,
        )
        for gen in child, parent, grandparent:
            with error.expected("ActiveRecord::RecordNotFound"):
                gen.action.delete()

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_add_service_parent(self, request, rest_api):
        """Tests adding parent reference to already existing service.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        parent = collection.action.create(service_body())[0]
        request.addfinalizer(parent.action.delete)
        child = collection.action.create(service_body())[0]
        child.action.edit(ancestry=str(parent.id))
        assert rest_api.response.status_code == 200
        child.reload()
        assert child.ancestry == str(parent.id)

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.meta(blockers=[BZ(1416903, forced_streams=['5.7', '5.8', 'upstream'])])
    def test_power_parent_service(self, request, rest_api, service_data):
        """Tests that power operations triggered on service parent affects child service.

        * start, stop and suspend actions
        * transition from one power state to another

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        service = collection.action.create(service_body())[0]
        request.addfinalizer(service.action.delete)
        child = collection.get(name=service_data['service_name'])
        vm = rest_api.collections.vms.get(name=service_data['vm_name'])
        child.action.edit(ancestry=str(service.id))
        child.reload()

        def _action_and_check(action, resulting_state):
            getattr(service.action, action)()
            assert rest_api.response.status_code == 200
            wait_for_vm_power_state(vm, resulting_state)

        wait_for_vm_power_state(vm, 'on')
        _action_and_check('stop', 'off')
        _action_and_check('start', 'on')
        _action_and_check('suspend', 'suspended')
        _action_and_check('start', 'on')

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_retire_parent_service_now(self, rest_api, service_data):
        """Tests that child service is retired together with a parent service.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.services
        parent = collection.action.create(service_body())[0]
        child = collection.get(name=service_data['service_name'])
        vm = rest_api.collections.vms.get(name=service_data['vm_name'])
        child.action.edit(ancestry=str(parent.id))
        child.reload()

        parent.action.retire()
        assert rest_api.response.status_code == 200
        wait_for(
            lambda: not collection.find_by(name=child.name),
            num_sec=600,
            delay=10,
        )
        wait_for(lambda: vm_retired(vm), num_sec=1000, delay=10)


class TestServiceDialogsRESTAPI(object):
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.parametrize("method", ["post", "delete"])
    def test_delete_service_dialog(self, rest_api, dialog, method):
        """Tests deleting service dialogs from detail.

        Metadata:
            test_flag: rest
        """
        status = 204 if method == "delete" else 200
        service_dialog = rest_api.collections.service_dialogs.get(label=dialog.label)
        service_dialog.action.delete(force_method=method)
        assert rest_api.response.status_code == status
        with error.expected("ActiveRecord::RecordNotFound"):
            service_dialog.action.delete(force_method=method)
        assert rest_api.response.status_code == 404

    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_delete_service_dialogs(self, rest_api, dialog):
        """Tests deleting service dialogs from collection.

        Metadata:
            test_flag: rest
        """
        service_dialog = rest_api.collections.service_dialogs.get(label=dialog.label)
        rest_api.collections.service_dialogs.action.delete(service_dialog)
        assert rest_api.response.status_code == 200
        with error.expected("ActiveRecord::RecordNotFound"):
            rest_api.collections.service_dialogs.action.delete(service_dialog)
        assert rest_api.response.status_code == 404


class TestServiceTemplateRESTAPI(object):
    def test_edit_service_template(self, rest_api, service_templates):
        """Tests editing a service template.
        Prerequisities:
            * An appliance with ``/api`` available.
        Steps:
            * POST /api/service_templates (method ``edit``) with the ``name``
            * Check if the service_template with ``new_name`` exists
        Metadata:
            test_flag: rest
        """
        for service_template in service_templates:
            new_name = fauxfactory.gen_alphanumeric()
            response = service_template.action.edit(name=new_name)
            assert rest_api.response.status_code == 200
            assert response.name == new_name
            service_template.reload()
            assert service_template.name == new_name

    def test_delete_service_templates(self, rest_api, service_templates):
        """Tests deleting service templates from collection.

        Metadata:
            test_flag: rest
        """
        rest_api.collections.service_templates.action.delete(*service_templates)
        assert rest_api.response.status_code == 200
        with error.expected("ActiveRecord::RecordNotFound"):
            rest_api.collections.service_templates.action.delete(*service_templates)
        assert rest_api.response.status_code == 404

    # POST method is not available on < 5.8, as described in BZ 1427338
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.8')
    def test_delete_service_template_post(self, rest_api, service_templates):
        """Tests deleting service templates from detail using POST method.

        Metadata:
            test_flag: rest
        """
        for service_template in service_templates:
            service_template.action.delete(force_method="post")
            assert rest_api.response.status_code == 200
            with error.expected("ActiveRecord::RecordNotFound"):
                service_template.action.delete(force_method="post")
            assert rest_api.response.status_code == 404

    def test_delete_service_template_delete(self, rest_api, service_templates):
        """Tests deleting service templates from detail using DELETE method.

        Metadata:
            test_flag: rest
        """
        for service_template in service_templates:
            service_template.action.delete(force_method="delete")
            assert rest_api.response.status_code == 204
            with error.expected("ActiveRecord::RecordNotFound"):
                service_template.action.delete(force_method="delete")
            assert rest_api.response.status_code == 404

    def test_assign_unassign_service_template_to_service_catalog(self, rest_api, service_catalogs,
            service_templates):
        """Tests assigning and unassigning the service templates to service catalog.
        Prerequisities:
            * An appliance with ``/api`` available.
        Steps:
            * POST /api/service_catalogs/<id>/service_templates (method ``assign``)
                with the list of dictionaries service templates list
            * Check if the service_templates were assigned to the service catalog
            * POST /api/service_catalogs/<id>/service_templates (method ``unassign``)
                with the list of dictionaries service templates list
            * Check if the service_templates were unassigned to the service catalog
        Metadata:
            test_flag: rest
        """

        scl = service_catalogs[0]
        stpl = service_templates[0]
        scl.service_templates.action.assign(stpl)
        assert rest_api.response.status_code == 200
        scl.reload()
        assert stpl.id in [st.id for st in scl.service_templates.all]
        scl.service_templates.action.unassign(stpl)
        assert rest_api.response.status_code == 200
        scl.reload()
        assert stpl.id not in [st.id for st in scl.service_templates.all]

    def test_edit_multiple_service_templates(self, rest_api, service_templates):
        """Tests editing multiple service catalogs at time.
        Prerequisities:
            * An appliance with ``/api`` available.
        Steps:
            * POST /api/service_templates (method ``edit``)
                with the list of dictionaries used to edit
            * Check if the service_templates with ``new_name`` each exists
        Metadata:
            test_flag: rest
        """
        new_names = []
        service_tpls_data_edited = []
        for tpl in service_templates:
            new_name = fauxfactory.gen_alphanumeric()
            new_names.append(new_name)
            service_tpls_data_edited.append({
                "href": tpl.href,
                "name": new_name,
            })
        response = rest_api.collections.service_templates.action.edit(*service_tpls_data_edited)
        assert rest_api.response.status_code == 200
        for i, resource in enumerate(response):
            assert resource.name == new_names[i]
            service_template = service_templates[i]
            service_template.reload()
            assert service_template.name == new_names[i]


class TestBlueprintsRESTAPI(object):
    @pytest.fixture(scope="function")
    def blueprints(self, request, rest_api):
        num = 2
        response = _blueprints(request, rest_api, num=num)
        assert rest_api.response.status_code == 200
        assert len(response) == num
        return response

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_create_blueprints(self, rest_api, blueprints):
        """Tests creation of blueprints.

        Metadata:
            test_flag: rest
        """
        for blueprint in blueprints:
            record = rest_api.collections.blueprints.get(id=blueprint.id)
            assert record.name == blueprint.name
            assert record.description == blueprint.description
            assert record.ui_properties == blueprint.ui_properties

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.parametrize("method", ["post", "delete"], ids=["POST", "DELETE"])
    def test_delete_blueprints_from_detail(self, rest_api, blueprints, method):
        """Tests deleting blueprints from detail.

        Metadata:
            test_flag: rest
        """
        status = 204 if method == "delete" else 200
        for blueprint in blueprints:
            blueprint.action.delete(force_method=method)
            assert rest_api.response.status_code == status
            with error.expected("ActiveRecord::RecordNotFound"):
                blueprint.action.delete(force_method=method)
            assert rest_api.response.status_code == 404

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_delete_blueprints_from_collection(self, rest_api, blueprints):
        """Tests deleting blueprints from collection.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.blueprints
        collection.action.delete(*blueprints)
        assert rest_api.response.status_code == 200
        with error.expected("ActiveRecord::RecordNotFound"):
            collection.action.delete(*blueprints)
        assert rest_api.response.status_code == 404

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_edit_blueprints(self, rest_api, blueprints, from_detail):
        """Tests editing of blueprints.

        Metadata:
            test_flag: rest
        """
        response_len = len(blueprints)
        new = [{
            'ui_properties': {
                'automate_entrypoints': {'Reconfigure': 'foo'}
            }
        } for _ in range(response_len)]
        if from_detail:
            edited = []
            for i in range(response_len):
                edited.append(blueprints[i].action.edit(**new[i]))
                assert rest_api.response.status_code == 200
        else:
            for i in range(response_len):
                new[i].update(blueprints[i]._ref_repr())
            edited = rest_api.collections.blueprints.action.edit(*new)
            assert rest_api.response.status_code == 200
        assert len(edited) == response_len
        for i in range(response_len):
            assert edited[i].ui_properties == new[i]['ui_properties']
            blueprints[i].reload()
            assert blueprints[i].ui_properties == new[i]['ui_properties']


class TestOrchestrationTemplatesRESTAPI(object):
    @pytest.fixture(scope='function')
    def orchestration_templates(self, request, rest_api):
        num = 2
        response = _orchestration_templates(request, rest_api, num=num)
        assert rest_api.response.status_code == 200
        assert len(response) == num
        return response

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_create_orchestration_templates(self, rest_api, orchestration_templates):
        """Tests creation of orchestration templates.

        Metadata:
            test_flag: rest
        """
        for template in orchestration_templates:
            record = rest_api.collections.orchestration_templates.get(id=template.id)
            assert record.name == template.name
            assert record.description == template.description
            assert record.type == template.type

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_delete_orchestration_templates_from_collection(
            self, rest_api, orchestration_templates):
        """Tests deleting orchestration templates from collection.

        Metadata:
            test_flag: rest
        """
        collection = rest_api.collections.orchestration_templates
        collection.action.delete(*orchestration_templates)
        assert rest_api.response.status_code == 200
        with error.expected("ActiveRecord::RecordNotFound"):
            collection.action.delete(*orchestration_templates)
        assert rest_api.response.status_code == 404

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.meta(blockers=[BZ(1414881, forced_streams=['5.7', '5.8', 'upstream'])])
    def test_delete_orchestration_templates_from_detail_post(self, orchestration_templates,
            rest_api):
        """Tests deleting orchestration templates from detail using POST method.

        Metadata:
            test_flag: rest
        """
        for ent in orchestration_templates:
            ent.action.delete(force_method="post")
            assert rest_api.response.status_code == 200
            with error.expected("ActiveRecord::RecordNotFound"):
                ent.action.delete(force_method="post")
            assert rest_api.response.status_code == 404

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    def test_delete_orchestration_templates_from_detail_delete(self, orchestration_templates,
            rest_api):
        """Tests deleting orchestration templates from detail using DELETE method.

        Metadata:
            test_flag: rest
        """
        for ent in orchestration_templates:
            ent.action.delete(force_method="delete")
            assert rest_api.response.status_code == 204
            with error.expected("ActiveRecord::RecordNotFound"):
                ent.action.delete(force_method="delete")
            assert rest_api.response.status_code == 404

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.7')
    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_edit_orchestration_templates(self, rest_api, orchestration_templates, from_detail):
        """Tests editing of orchestration templates.

        Metadata:
            test_flag: rest
        """
        response_len = len(orchestration_templates)
        new = [{
            'description': 'Updated Test Template {}'.format(fauxfactory.gen_alphanumeric(5))
        } for _ in range(response_len)]
        if from_detail:
            edited = []
            for i in range(response_len):
                edited.append(orchestration_templates[i].action.edit(**new[i]))
                assert rest_api.response.status_code == 200
        else:
            for i in range(response_len):
                new[i].update(orchestration_templates[i]._ref_repr())
            edited = rest_api.collections.orchestration_templates.action.edit(*new)
            assert rest_api.response.status_code == 200
        assert len(edited) == response_len
        for i in range(response_len):
            assert edited[i].description == new[i]['description']
            orchestration_templates[i].reload()
            assert orchestration_templates[i].description == new[i]['description']

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.8')
    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_copy_orchestration_templates(self, request, rest_api, orchestration_templates,
            from_detail):
        """Tests copying of orchestration templates.

        Metadata:
            test_flag: rest
        """
        num_orch_templates = len(orchestration_templates)
        new = []
        for _ in range(num_orch_templates):
            uniq = fauxfactory.gen_alphanumeric(5)
            new.append({
                "name": "test_copied_{}".format(uniq),
                "content": "{{ 'Description' : '{}' }}\n".format(uniq)
            })
        if from_detail:
            copied = []
            for i in range(num_orch_templates):
                copied.append(orchestration_templates[i].action.copy(**new[i]))
                assert rest_api.response.status_code == 200
        else:
            for i in range(num_orch_templates):
                new[i].update(orchestration_templates[i]._ref_repr())
            copied = rest_api.collections.orchestration_templates.action.copy(*new)
            assert rest_api.response.status_code == 200

        request.addfinalizer(
            lambda: rest_api.collections.orchestration_templates.action.delete(*copied))

        assert len(copied) == num_orch_templates
        for i in range(num_orch_templates):
            orchestration_templates[i].reload()
            assert copied[i].name == new[i]['name']
            assert orchestration_templates[i].id != copied[i].id
            assert orchestration_templates[i].name != copied[i].name
            assert orchestration_templates[i].description == copied[i].description
            new_record = rest_api.collections.orchestration_templates.get(id=copied[i].id)
            assert new_record.name == copied[i].name

    @pytest.mark.tier(3)
    @pytest.mark.uncollectif(lambda: version.current_version() < '5.8')
    @pytest.mark.parametrize(
        "from_detail", [True, False],
        ids=["from_detail", "from_collection"])
    def test_invalid_copy_orchestration_templates(self, rest_api, orchestration_templates,
            from_detail):
        """Tests copying of orchestration templates without changing content.

        Metadata:
            test_flag: rest
        """
        num_orch_templates = len(orchestration_templates)
        new = []
        for _ in range(num_orch_templates):
            new.append({
                "name": "test_copied_{}".format(fauxfactory.gen_alphanumeric(5))
            })
        if from_detail:
            for i in range(num_orch_templates):
                with error.expected("content must be unique"):
                    orchestration_templates[i].action.copy(**new[i])
                assert rest_api.response.status_code == 400
        else:
            for i in range(num_orch_templates):
                new[i].update(orchestration_templates[i]._ref_repr())
            with error.expected("content must be unique"):
                rest_api.collections.orchestration_templates.action.copy(*new)
            assert rest_api.response.status_code == 400
