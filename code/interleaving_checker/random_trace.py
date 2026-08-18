from dataclasses import dataclass
from typing import Literal

from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation, ClientOperation
from device.serverdevice import ServerDevice
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)
from unique_char.uniquechar import UniqueChar


class Character:
    char: UniqueChar
    left_origin: UniqueChar | Literal['start']
    right_origin: UniqueChar | Literal['end']
    left_origin_of: list[UniqueChar]
    right_origin_of: list[UniqueChar]

    def __init__(self, char: UniqueChar, left_origin: UniqueChar | Literal['start'], right_origin: UniqueChar | Literal['end']):
        self.char = char
        self.left_origin = left_origin
        self.right_origin = right_origin
        self.left_origin_of = []
        self.right_origin_of = []

    def add_to_right_origin_of(self, char: UniqueChar):
        self.right_origin_of.append(char)

    def add_to_left_origin_of(self, char: UniqueChar):
        self.left_origin_of.append(char)

    def __str__(self) -> str:
        return f'''Char: {self.char}
                   Left: {self.left_origin} 
                   Right: {self.right_origin}
                   LeftOf: {self.left_origin_of}
                   RightOf: {self.right_origin_of} '''

class ClientTrace:
    events_seen: list[Event]
    states_after_events: list[list[UniqueChar]]

    def __init__(self):
        self.events_seen = []
        self.states_after_events = []

    def add_event(self, event: Event, state: list[UniqueChar]) -> None:
        self.events_seen.append(event)
        self.states_after_events.append(list(state))


@dataclass
class Event:
    operation: list[ClientInsertOperation | ClientDeleteOperation]
    performed_locally: bool
    
def build_random_trace_clients(clients: dict[int, ClientDevice], num_of_operations: int = 30, print_ops:bool=False) -> tuple[dict[int, ClientTrace], dict[int, Character]]: 
    client_traces: dict[int, ClientTrace] = {}

    characters: dict[int, Character] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()
    
    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()), with_deletes=False)
       
        client = clients[operation.client_id]
        if print_ops:
            print(operation)
        operation_seen = client.perform_operation(operation)

        assert not isinstance(operation_seen, ClientDeleteOperation)

        state = list(client.read_state())
        if isinstance(operation, ClientInsertOperation):
            char = operation.character

            left_origin = state[operation.position - 1] if operation.position > 0 else 'start'
            right_origin = state[operation.position + 1]  if operation.position < len(state) - 1 else 'end' 

            if left_origin != 'start':
                left_origin_character = characters[left_origin.id]
                left_origin_character.add_to_left_origin_of(char)

            if right_origin != 'end':
                right_origin_character = characters[right_origin.id]
                right_origin_character.add_to_right_origin_of(char)

            character = Character(char, left_origin, right_origin)

            characters[character.char.id] = character

        if len(operation_seen) != 0:
            performed_locally = isinstance(operation, ClientInsertOperation)
            client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), state)
    
    return client_traces, characters

def build_random_trace_client_server(clients: dict[int, ClientDevice], server: ServerDevice, num_of_operations: int = 30, print_ops:bool=False) -> tuple[dict[int, ClientTrace], dict[int, Character]]: 
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()

    characters: dict[int, Character] = {}
    
    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()), with_deletes=False)
        if print_ops:
            print(operation)
        if  isinstance(operation, ClientOperation):
            client = clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            assert not isinstance(operation_seen, ClientDeleteOperation)

            state = list(client.read_state())

            if isinstance(operation, ClientInsertOperation):
                char = operation.character

                left_origin = state[operation.position - 1] if operation.position > 0 else 'start'
                right_origin = state[operation.position + 1]  if operation.position < len(state) - 1 else 'end' 

                if left_origin != 'start':
                    left_origin_character = characters[left_origin.id]
                    left_origin_character.add_to_left_origin_of(char)

                if right_origin != 'end':
                    right_origin_character = characters[right_origin.id]
                    right_origin_character.add_to_right_origin_of(char)

                character = Character(char, left_origin, right_origin)

                characters[character.char.id] = character

            if len(operation_seen) != 0:
                performed_locally = isinstance(operation, ClientInsertOperation)
                client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), state)
        else:
            server.perform_operation(operation)
            if print_ops:
                print("SERVER: ", *server.read_state(), sep="")
    
    return client_traces, characters

    
def build_random_trace(clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_operations: int = 30, print_ops:bool=False) -> tuple[dict[int, ClientTrace], dict[int, Character]]:
    if server:
        return build_random_trace_client_server(clients, server, num_of_operations, print_ops)
    else:
        return build_random_trace_clients(clients, num_of_operations, print_ops)