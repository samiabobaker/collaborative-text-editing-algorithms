from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientInsertOperation, ClientOperation
from device.serverdevice import ServerDevice
from list_spec_checker.client_trace import ClientTrace, Event
from random_operation_generator.random_operation_generator import (
    generate_random_client_client_operation,
    generate_random_client_server_operation,
)


def build_random_trace_clients(clients: dict[int, ClientDevice], num_of_operations: int = 30,print_ops:bool=False): 
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()
    
    for _ in range(num_of_operations):
        operation = generate_random_client_client_operation(list(clients.values()))
        client = clients[operation.client_id]
        operation_seen = client.perform_operation(operation)

        if len(operation_seen) != 0:
            performed_locally = isinstance(operation, ClientInsertOperation | ClientDeleteOperation)
            client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), list(client.read_state()))
        if print_ops:
            print(operation)
    
    return client_traces

def build_random_trace_client_server(clients: dict[int, ClientDevice], server: ServerDevice, num_of_operations: int = 30,print_ops:bool=False): 
    client_traces: dict[int, ClientTrace] = {}

    for client_id in clients:
        client_traces[client_id] = ClientTrace()
    
    for _ in range(num_of_operations):
        operation = generate_random_client_server_operation(server, list(clients.values()))
        if print_ops:
            print(operation)
        if  isinstance(operation, ClientOperation):
            client = clients[operation.client_id]
            operation_seen = client.perform_operation(operation)

            if len(operation_seen) != 0:
                performed_locally = isinstance(operation, ClientInsertOperation | ClientDeleteOperation)
                client_traces[operation.client_id].add_event(Event(operation_seen, performed_locally), list(client.read_state()))
        else:
            server.perform_operation(operation)
    
    return client_traces

def build_random_trace(clients: dict[int, ClientDevice], server: ServerDevice | None = None, num_of_operations: int = 30,print_ops:bool=False) -> dict[int, ClientTrace]:
    if server:
        return build_random_trace_client_server(clients, server, num_of_operations,print_ops)
    else:
        return build_random_trace_clients(clients, num_of_operations,print_ops)