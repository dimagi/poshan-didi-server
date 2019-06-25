import csv
import json

from simple_settings import settings


class State():
    def __init__(self, uuid, msg_id, children):
        self.children = children
        self.msg_id = msg_id
        self.parent = None
        self.id = uuid

    def has_children(self):
        return self.children != None


class StateMachine(object):
    def __init__(self, flow_filename, messages_filename):
        # All of these maps have the state shortname (which is also the
        # msg_id for a state) as the key and the action or text as the value.
        # We could generalize this to some Action class or something, but we're
        # not. It's fine.
        self.uttering_map_en = {}
        self.uttering_map_hi = {}
        self.images_map = {}

        self.root_uuid = None
        self.states = []
        self.load_state_machine(flow_filename, messages_filename)

    def load_state_machine(self, flow_filename, messages_filename):
        self._load_messages(messages_filename)
        self._load_flows(flow_filename)

    def get_start_state(self):
        return self.find_state(self.root_uuid)

    def get_msg_and_next_state(self, current_state_id, intent):
        intent = str(int(intent))
        if current_state_id is None:
            next_state = self.get_start_state()
        else:
            current_state = self.find_state(current_state_id)
            try:
                next_state = self.find_state(
                    current_state.children[intent])
            except KeyError:
                raise ValueError(
                    f'No such transition for {intent} from state {current_state.id}. Valid transitions: {current_state.children}')
        msg_id = next_state.msg_id
        state_id = next_state.id
        if not next_state.has_children():
            next_state = None
        return self.get_messages_from_state_name(msg_id), self.get_images_from_state_name(msg_id), state_id, msg_id

    def get_state_id_from_state_name(self, state_name):
        node = self.find_state_by_name(state_name)
        return node.id

    def get_messages_from_state_name(self, state_name):
        if settings.HINDI:
            return self.uttering_map_hi[state_name]
        return self.uttering_map_en[state_name]

    def get_images_from_state_name(self, state_name):
        try:
            return self.images_map[state_name]
        except KeyError:
            return None

    def _check_and_add(self, the_map, key, value):
        if key not in the_map.keys():
            the_map[key] = []
        the_map[key].append(value)
        return the_map

    def _load_messages(self, messages_filename):
        with open(messages_filename) as f:
            csv_rdr = csv.DictReader(f)
            for row in csv_rdr:
                row['message_shortname'] = row['message_shortname'].replace(
                    ' ', '_')
                self.uttering_map_en = self._check_and_add(self.uttering_map_en,
                                                           row['message_shortname'],
                                                           row['english'])
                self.uttering_map_hi = self._check_and_add(self.uttering_map_hi,
                                                           row['message_shortname'],
                                                           row['hindi'])
                self.images_map = self._check_and_add(self.images_map,
                                                      row['message_shortname'],
                                                      row['image'])

    def _load_flows(self, flow_filename):
        with open(flow_filename) as f:
            flow_list = json.load(f)
            if len(flow_list['flows']) != 1:
                raise ValueError(
                    f'Flow file must contain only a single flow. {flow_filename} contains {len(flow_list["flows"])} flows!')

            # Select the single flow and load in all of the 'state transitions' from the "rule sets" section
            flow = flow_list['flows'][0]
            transitions = {}
            for transition in flow['rule_sets']:
                transitions[transition['uuid']] = {r['test']['test']['base']: r['destination']
                                                   for r in transition['rules'] if 'test' in r['test'].keys()}

            self.root_uuid = flow['entry']
            self.states = []
            for node in flow['action_sets']:
                try:
                    children = transitions[node['destination']]
                except:
                    children = None

                # currently only support a single action. This means if our
                # colleagues put in multiple actions for a given state (e.g.,
                # send an image and send text) it is ignored. We rather use
                # the translations file to define all of the actions for a
                # given state.
                new_node = State(node['uuid'],
                                 node['actions'][0]['msg']['base'],
                                 children)
                self.states.append(new_node)

            # Complete setup
            self._set_state_parents()

    def _set_state_parents(self):
        """Go through all of the states and link children back to their parents"""
        for node in self.states:
            if node.has_children():
                for _, child_uuid in node.children.items():
                    if child_uuid is not None:
                        self.find_state(child_uuid).parent = node

    def find_state(self, uuid):
        #  Nothing smart, because who cares?
        for n in self.states:
            if n.id == uuid:
                return n
        raise ValueError(f'Unable to find node: {uuid}')

    def find_state_by_name(self, name):
        #  Nothing smart, because who cares?
        for n in self.states:
            if n.msg_id == name:
                return n
        raise ValueError(f'Unable to find node by name: {name}')
