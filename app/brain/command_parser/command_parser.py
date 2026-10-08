from app.brain.command_parser.command import Command
from app.brain.command_parser.action_parser import ActionParser
from app.brain.command_parser.entity_parser import EntityParser
from app.brain.entity_mapper.entity_mapper import EntityMapper


class CommandParser:

    def __init__(self):

        self.action_parser = ActionParser()
        self.entity_parser = EntityParser()
        self.entity_mapper = EntityMapper()

    # ----------------------------------------

    def parse(self, text):

        command = Command()

        command.action = self.action_parser.parse(text)

        entity = self.entity_parser.parse(text)

        command.entity = self.entity_mapper.map(entity)

        return command