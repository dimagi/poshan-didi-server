import csv
import json
import re

from simple_settings import settings

UUID_RE = re.compile(
    r'^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$')


class Node():
    def __init__(self, type, uuid, destination_uuid=None, state_name=None, transitions={}):
        self.type = type
        self.uuid = uuid
        self.destination_uuid = destination_uuid
        self.state_name = state_name
        self.transitions = transitions
        self.terminal = False
        self.immediate = False
        self.msgs_hi_male = []
        self.msgs_hi_female = []
        self.msgs_en = []
        self.images = []

    def add_hi_msg(self, msg, msg_male=None, msg_female=None):
        msg_male = msg_male or msg
        msg_female = msg_female or msg
        self.msgs_hi_male.append(msg_male)
        self.msgs_hi_female.append(msg_female)

    def add_en_msg(self, msg):
        self.msgs_en.append(msg)

    def add_img(self, img):
        if img:
            self.images.append(img)

    def get_messages_and_images(self, gender):
        # default to english
        msgs = self.msgs_en
        if settings.HINDI:
            if gender == 'M':
                msgs = self.msgs_hi_male
            elif gender == 'F':
                msgs = self.msgs_hi_female
            else:
                raise ValueError(
                    f'Gender: "{gender}" unrecognized. Should be M or F')
        return msgs, self.images


class StateMachine(object):
    def __init__(self, flow_filename, messages_filename):
        # All of these maps have the state shortname (which is also the
        # state_name for a state) as the key and the action or text as the value.
        # We could generalize this to some Action class or something, but we're
        # not. It's fine.
        self.direct_to_nurse_states = []

        self.root_uuid = None
        self.states = []
        self.load_state_machine(flow_filename, messages_filename)

    def load_state_machine(self, flow_filename, messages_filename):
        self._load_flows(flow_filename)
        self._load_messages(messages_filename)

    def get_start_state(self):
        return self._find_state_by_uuid(self.root_uuid)

    def _is_UUID(self, uuid):
        return uuid and UUID_RE.match(uuid)

    def get_msg_and_next_state(self, current_state_id, gender, intent=None):
        if intent:
            intent = str(int(intent))

        state_name, state_id, terminal = None, None, True

        if current_state_id is None:
            next_state = self.get_start_state()
        else:
            # Same state
            if self._is_UUID(current_state_id):
                current_state = self._find_state_by_uuid(current_state_id)
            else:
                current_state = self._find_state_by_name(current_state_id)
            if intent is None:
                next_state = current_state
            elif len(current_state.transitions) > 0:
                try:
                    next_state = self._find_state_by_uuid(
                        current_state.transitions[intent])
                except KeyError:
                    raise ValueError(
                        f'No such transition for {intent} from state {current_state.uuid}. Valid transitions: {current_state.transitions}')
            else:
                next_state = None

            # Loop through all the auto-state transitions
            msgs, imgs = [], []
            if next_state is not None:
                msgs, imgs = self._get_msgs_and_imgs_from_state_name(
                    next_state.state_name, gender)
                while next_state is not None and next_state.immediate:
                    next_state = self._find_state_by_uuid(
                        next_state.destination_uuid)
                    m, i = self._get_msgs_and_imgs_from_state_name(
                        next_state.state_name, gender)
                    msgs = msgs + m
                    imgs = imgs + i

        if next_state:
            state_name = next_state.state_name
            state_id = next_state.uuid
            terminal = next_state.terminal
        return msgs, imgs, state_id, state_name, terminal

    def is_nurse_state(self, state_name):
        return state_name in self.direct_to_nurse_states

    def get_state_id_from_state_name(self, state_name):
        node = self._find_state_by_name(state_name)
        return node.uuid

    def _get_msgs_and_imgs_from_state_name(self, state_name, gender):
        if state_name is None:
            return [], []

        if state_name == 'custom_gm':
            return [state_name], [state_name]

        state = self._find_state_by_name(state_name)
        return state.get_messages_and_images(gender)

    def _add_content_to_state(self, state_name, msg_en, msg_hi, msg_hi_m, msg_hi_f, image):
        msg_hi_m = msg_hi_m if len(msg_hi_m) > 0 else None
        msg_hi_f = msg_hi_f if len(msg_hi_f) > 0 else None
        image = image if len(image) > 0 else None
        state = self._find_state_by_name(state_name)
        state.add_en_msg(msg_en)
        state.add_hi_msg(msg_hi, msg_hi_m, msg_hi_f)
        state.add_img(image)

    def _load_messages(self, messages_filename):
        with open(messages_filename) as f:
            csv_rdr = csv.DictReader(f)
            for row in csv_rdr:
                row['message_shortname'] = row['message_shortname'].replace(
                    ' ', '_')
                if row['direct_to_nurse'].lower() == 'yes':
                    self.direct_to_nurse_states.append(
                        row['message_shortname'])

                self._add_content_to_state(
                    row['message_shortname'],  # State name
                    row['english'],
                    row['hindi'],
                    row['hindi_male'],
                    row['hindi_female'],
                    row['image']
                )

    def _load_flows(self, flow_filename):
        with open(flow_filename, 'r') as f:
            flow_list = json.load(f)
            if len(flow_list['flows']) != 1:
                raise ValueError(
                    f'Flow file must contain only a single flow. {flow_filename} contains {len(flow_list["flows"])} flows!')

            # Grab the first flow
            flow = flow_list['flows'][0]
            self.root_uuid = flow['entry']

            self.nodes = []
            self.parent_map = {}
            for action_set in flow['action_sets']:
                self.parent_map[action_set['uuid']
                                ] = action_set['actions'][0]['uuid']
                num_actions = len(action_set['actions'])
                for idx, action in enumerate(action_set['actions']):
                    # If this is not the final action, then peak ahead and set the transition.
                    dest_uuid = action_set['destination']
                    if idx+1 < num_actions:
                        dest_uuid = action_set['actions'][idx+1]['uuid']
                    n = Node(
                        'state', action['uuid'], dest_uuid, state_name=action['msg']['base'])
                    self.nodes.append(n)

            for rule_set in flow['rule_sets']:
                transitions = {}
                for rule in rule_set['rules']:
                    if 'test' in rule['test'].keys():
                        transitions[rule['test']['test']
                                    ['base']] = rule['destination']
                self.nodes.append(Node(
                    'transition',
                    rule_set['uuid'],
                    transitions=transitions
                ))
        self._create_states()

    def _create_states(self):
        self.states = []
        for n in self.nodes:
            if n.type == 'transition':
                continue

            dest = self._find_node_by_uuid(n.destination_uuid)
            if dest is None:
                n.terminal = True
            elif dest.type == 'transition':
                n.transitions = dest.transitions.copy()
                # Update destinations
                for intent, child in n.transitions.items():
                    child_node = self._find_node_by_uuid(child)
                    n.transitions[intent] = child_node.uuid
            elif dest.type == 'state':
                n.immediate = True
                n.destination_uuid = dest.uuid

            self.states.append(n)

    def _find_node_by_uuid(self, uuid):
        if uuid in self.parent_map.keys():
            return self._find_node_by_uuid(self.parent_map[uuid])
        for n in self.nodes:
            if n.uuid == uuid:
                return n
        return None

    def _find_state_by_uuid(self, uuid):
        for s in self.states:
            if s.uuid == uuid:
                return s
        return None

    def _find_state_by_name(self, state_name):
        for s in self.states:
            if s.state_name == state_name:
                return s
        return None

    def get_submodule_state_name(self, prefix):
        # Take advantage of our naming scheme to find the correct submodule menu.
        options = [state.state_name for state in self.states
                   if state.state_name.startswith(prefix)]
        options.sort()
        return options[-1]
