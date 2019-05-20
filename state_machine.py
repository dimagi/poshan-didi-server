import csv
import json
from fuzzywuzzy import fuzz


def str2key(s):
    x = s.split()
    return ''.join(x).lower()


class State():
    def __init__(self, uuid, msg_id, children):
        self.children = children
        self.msg_id = msg_id
        self.parent = None
        self.id = uuid

    def has_children(self):
        return self.children != None


# TODO: Get rid of the fuzzy matching stuff 
class StateMachine(object):
    def __init__(self, flow_filename, messages_filename):
        self.msg_map, self.uttering_map_en = {}, {}
        self.root_uuid = None
        self.states = []
        self.load_state_machine(flow_filename, messages_filename)

    def load_state_machine(self, flow_filename, messages_filename):
        self._load_messages(messages_filename)
        self._load_flows(flow_filename)

    def get_start_state(self):
        return self.find_state(self.root_uuid)

    def get_msg_and_next_state(self, current_state, intent):
        intent = str(int(intent))
        if current_state is None:
            next_state = self.get_start_state()
        else:
            # current_state = self.find_state(current_state_id)
            try:
                next_state = self.find_state(
                    current_state.children[intent])
            except KeyError:
                raise ValueError(
                    f'No such transition for {intent} from state {current_state.id}. Valid transitions: {current_state.children}')
        msg = next_state.msg_id
        if not next_state.has_children():
            next_state = None
        return self._get_message(msg), next_state

    def _get_message(self, msg_id):
        return self.uttering_map_en[msg_id]

    def _load_messages(self, messages_filename):
        with open(messages_filename) as f:
            csv_rdr = csv.DictReader(f)
            for row in csv_rdr:
                row['message_shortname'] = row['message_shortname'].replace(
                    ' ', '_')
                self.msg_map[
                    str2key(row['english'])] = row['message_shortname']
                self.uttering_map_en[row['message_shortname']] = row['english']

    def _load_flows(self, flow_filename):
        with open(flow_filename) as f:
            flow_list = json.load(f)
            if len(flow_list['flows']) != 1:
                raise ValueError(
                    f'Flow file must contain only a single flow. {flow_filename} contains {len(flow_list["flows"])} flows!')
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
                # currently only support a single action
                key = str2key(node['actions'][0]['msg']['base'])
                keys_list = list(self.msg_map.keys())
                scores = [fuzz.ratio(key, k) for k in keys_list]
                if max(scores) < 90:
                    # if key not in msg_map.keys():
                    print(max(scores))
                    print(f'error, cannot find: {key}')
                    continue

                new_node = State(node['uuid'],
                                 self.msg_map[keys_list[scores.index(max(scores))]], children)
                self.states.append(new_node)

            # Complete setup
            self._set_state_parents()

    def _set_state_parents(self):
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
