# TODO: clean up.
class Tree():
    def __init__(self, root_uuid, nodes):
        self.root_uuid = root_uuid
        self.nodes = nodes
        self.rasa_lookup = {
            '1': 'option_one',
            '2': 'option_two',
            '3': 'option_three',
            '4': 'option_four',
            '5': 'option_five',
            '6': 'option_six',
            '7': 'option_seven',
            '8': 'option_eight',
            '9': 'option_nine',
        }

    def find_node(self, uuid):
        #  Nothing smart, because who cares?
        for n in self.nodes:
            if n.id == uuid:
                return n
        raise ValueError(f'Unable to find node: {uuid}')

    def set_parents(self):
        for node in self.nodes:
            if node.has_children():
                for _, child in node.children.items():
                    if child is not None:
                        self.find_node(child).parent = node

    def pprint(self):
        root = self.find_node(self.root_uuid)
        indent_level = 0
        self.print_node(root, '', indent_level)

    def print_node(self, node, prefix, indent_level):
        if node.has_children():
            print(' '*indent_level + prefix + str(node.id) + ' ->')
            for option, child in node.children.items():
                if child is not None:
                    self.print_node(self.find_node(child),
                                    f'[{option}] ', indent_level+4)
        else:
            print(' '*indent_level + prefix + str(node.id) + ' *')

    def pprint_paths(self):
        root = self.find_node(self.root_uuid)
        self.print_leaf_paths(root, '')

    def print_leaf_paths(self, node, path):
        if node.has_children():
            for _, child in node.children.items():
                if child is not None:
                    self.print_leaf_paths(
                        self.find_node(child), f'{path}/{node.id}')
        else:
            print(f'{path}/{node.id}')

    def print_rasa_stories(self):
        root = self.find_node(self.root_uuid)
        self.print_rasa_leaf_story(root, '')

    def print_rasa_leaf_story(self, node, story):
        if node.has_children():
            for option, child in node.children.items():
                if child is not None:
                    self.print_rasa_leaf_story(
                        self.find_node(child), story + f'\n- utter_{node.msg}\n* {self.rasa_lookup[option]}')
        else:
            print(f'## story_{node.msg}{story}\n- utter_{node.msg}\n')

    def save_rasa_stories(self, first_action=''):
        if len(first_action) > 0 and first_action[0] != '\n':
            first_action = f'\n{first_action}'
        root = self.find_node(self.root_uuid)
        return self.rasa_leaf_story_string(root, '', first_action)

    def rasa_leaf_story_string(self, node, story, first_action=''):
        if node.has_children():
            stories = ''
            for option, child in node.children.items():
                if child is not None:
                    stories = stories + self.rasa_leaf_story_string(
                        self.find_node(child),
                        story +
                        f'\n- utter_{node.msg}\n* {self.rasa_lookup[option]}',
                        first_action)
            return stories
        else:
            return f'## story_{node.msg}{first_action}{story}\n- utter_{node.msg}\n\n'


class Node():
    def __init__(self, uuid, msg, children):
        self.children = children
        self.msg = msg
        self.parent = None
        self.id = uuid

    def has_children(self):
        return self.children != None
