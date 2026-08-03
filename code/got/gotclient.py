from device.clientdevice import ClientDevice
from device.operations import ClientDeleteOperation, ClientOperation, ClientReceiveFromServerOperation, ClientReceiveFromClientOperation, ClientTimestepOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar
from got.gotmessage import GOTMessage
from got.operations.operation import GOTOperation
from got.operations.delete import GOTDeleteOperation
from got.operations.insert import GOTInsertOperation
from got.operations.split_delete import GOTSplitDeleteOperation

from got.transformations.inclusion import InclusionTransformer
from got.transformations.exclusion import ExclusionTransformer
from got.transformations.original.original_exclusion import OriginalExclusionTransformer
from got.transformations.original.original_inclusion import OriginalInclusionTransformer



class GOTClient(ClientDevice):
    client_id : int
    state: list[UniqueChar]

    clients: list[GOTClient]
    vector_clock: dict[int, int]
    message_buffer: dict[int, list[GOTMessage]]

    _history_buffer : list[GOTOperation]

    inclusion_transformer: InclusionTransformer
    exclusion_transformer: ExclusionTransformer
    


    def __init__(self, client_id: int):
        self.client_id = client_id
        self.state = []
        self._history_buffer = []

        self.inclusion_transformer = OriginalInclusionTransformer()
        self.exclusion_transformer = OriginalExclusionTransformer()

    def get_state(self) -> list[UniqueChar]:
        return self.state

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
            match operation:
                case ClientInsertOperation():
                    self.perform_local_insert(operation)
                    return [operation]
                case ClientDeleteOperation():
                    self.perform_local_delete(operation)
                    return [operation]
                case ClientReceiveFromServerOperation():
                    return []
                case ClientReceiveFromClientOperation(_, sender_client_id):
                    return self.receive_from_client(sender_client_id)
                case ClientTimestepOperation():
                    return []
                case _ as unreachable:
                    assert_never(unreachable)

    def receive_from_client(self, client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
            #Check if message from client exists, and is causally ready.
            client_message_buffer = self.message_buffer[client_id]
    
            if len(client_message_buffer) == 0:
                return []
            
            if not self.__is_causally_ready(client_message_buffer[0].operation):
                return []
            
            message = client_message_buffer.pop(0)
    
            self._apply_operation(message.operation)
    
            return [message.causing_operation]


    def perform_local_insert(self, operation: ClientInsertOperation) -> GOTInsertOperation:
        """
        Generates a local insert operation, applies it to the current document,
        and returns the operation.

        Parameters
        ----------
        sequence (str):
            The string to insert.
        idx (int):
            The index at which to insert the string.

        Returns
        -------
        GOTInsertOperation:
            The insert operation that was performed.
        """
        insert_operation = self._generate_insert(sequence=[operation.character], idx=operation.position)
        self._apply_operation_to_document(insert_operation)
        self.__send_to_other_clients(GOTMessage(insert_operation, operation))

        return insert_operation

    def perform_local_delete(self, operation: ClientDeleteOperation) -> GOTDeleteOperation:
        """
        Generates a local delete operation, applies it to the current document,
        and returns the operation.

        Parameters
        ----------
        num_to_delete (int):
            The number of characters to delete.
        idx (int):
            The starting index at which to delete the characters.

        Returns
        -------
        GOTDeleteOperation:
            The delete operation that was performed.
        """
        delete_operation = self._generate_delete(num_to_delete=1, idx=operation.position)
        self._apply_operation_to_document(delete_operation)
        self.__send_to_other_clients(GOTMessage(delete_operation, operation))
        
        return delete_operation

    def _generate_insert(self, sequence: list[UniqueChar], idx: int) -> GOTInsertOperation:
        """Generates a local insert operation and increments the state vector at the client's index."""
        sv = self.vector_clock.copy()
        sv[self.client_id] += 1

        return GOTInsertOperation(idx, sequence, self.client_id, sv)

    def _generate_delete(self, num_to_delete: int, idx: int) -> GOTDeleteOperation:
        """Generates a local delete operation and increments the state vector at the client's index."""
        sv = self.vector_clock.copy()
        sv[self.client_id] += 1

        return GOTDeleteOperation(
            num_to_delete,
            idx,
            sequence=self.get_state()[idx : idx + num_to_delete],
            client_id=self.client_id,
            state_vector=sv,
        )

    def send_message(self, client_id: int, message: GOTMessage):
            self.message_buffer[client_id].append(message)
        
    def __send_to_other_clients(self, message: GOTMessage) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, message)
    

    def read_state(self) -> list[UniqueChar]:
        return self.state

    def can_receive_from_server(self) -> bool:
        return False

    def set_clients(self, clients: list[GOTClient]) -> None:
            self.clients = clients
            self.vector_clock = {}
            self.message_buffer = {}
            for client in clients:
                self.vector_clock[client.client_id] = 0
                self.message_buffer[client.client_id] = []


    def _apply_operation(self, incoming: GOTOperation) -> bool:
            """
            Follows the Generic Operational Transformation (GOT) algorithm:
    
            1. Undo all operations in the history buffer from right to left until an operation EO_m is found
               such that EO_m is *totally ordered* with respect to the incoming operation.
            2. Apply the incoming operation using the GOT control algorithm
            3. Transform each operation EO_{m + 1}, ..., EO_n in the history buffer
            4. Redo the transformed operations
    
            Parameters
            ----------
            incoming : Operation
                The operation that is to be executed.
    
            Returns
            -------
            bool
                Returns `True` if the operation was applied, `False` if the operation is not causally-ready to be applied.
            """
            # Sanitise the incoming operation from any internal state to avoid any side effects
            incoming_operation = incoming.remove_all_metadata()
    
            if not self.__is_causally_ready(incoming_operation):
                return False
    
            # Undo all operations in the HB from right to left that are not totally ordered with the incoming operation.
            undone_operations = self._undo_non_totally_ordered_operations(incoming_operation)
    
            all_causally_ordered, first_independent_idx = self._check_all_operations_causally_ordered(incoming_operation)
    
            if all_causally_ordered:
                # No transformation needed---simply apply the incoming operation
                transformed = incoming_operation
            else:
                # Using the same terminology as in the paper, `EOL` is the list of all operations from
                # `HB[first_independent_idx + 1 : ]` that causally precede the incoming operation.
                EOL = self._find_all_causally_ordered_operations_from(first_independent_idx + 1, incoming_operation)
    
                if len(EOL) == 0:
                    # Easy case: all subsequent operations are independent to the incoming operation, so `incoming_operation`
                    # and `history_buffer[first_independent_idx]` are context-equivalent.
                    # We simply include the effect of `history_buffer[first_independent_idx : ]` on `incoming_operation`
                    transformed = self.inclusion_transformer.list_inclusion_transform(
                        incoming_operation, self._history_buffer[first_independent_idx:]
                    )
                else:
                    # Some operations after the first independent operation causally precede the incoming operation
                    EOL_prime: list[GOTOperation] = []
    
                    for op_index, causally_preceding_op in EOL:
                        # Exclude the effect of all operations between `first_independent_idx` and `i` (inclusive)
                        excluded_against_prev = self.exclusion_transformer.list_exclusion_transform(
                            causally_preceding_op,
                            list(reversed(self._history_buffer[first_independent_idx:op_index])),
                        )
    
                        if len(EOL_prime) == 0:
                            if isinstance(excluded_against_prev, GOTSplitDeleteOperation):
                                EOL_prime.extend(self._flatten_and_transform_split_operation(excluded_against_prev))
                            else:
                                EOL_prime.append(excluded_against_prev)
                        else:
                            included = self.inclusion_transformer.list_inclusion_transform(excluded_against_prev, EOL_prime)
                            if isinstance(included, GOTSplitDeleteOperation):
                                EOL_prime.extend(self._flatten_and_transform_split_operation(included))
                            else:
                                EOL_prime.append(included)
    
                    # Exclude the effect of all operations in EOL_prime from incoming_operation
                    incoming_excluded = self.exclusion_transformer.list_exclusion_transform(
                        incoming_operation, list(reversed(EOL_prime))
                    )
    
                    # Now transform the result to include the effect of all operations in the HB after first_independent_idx
                    transformed = self.inclusion_transformer.list_inclusion_transform(
                        incoming_excluded, self._history_buffer[first_independent_idx:]
                    )
    
            self._apply_operation_to_document(transformed)
    
            self._redo_undone_operations(undone_operations, transformed)
    
            return True
    

    def __is_causally_ready(self, incoming: GOTOperation) -> bool:
        if incoming.state_vector[incoming.client_id] != self.vector_clock[incoming.client_id] + 1:
            return False

        for client_id in self.vector_clock:
             if client_id == incoming.client_id:
                  continue

             if incoming.state_vector[client_id] > self.vector_clock[client_id]:
                  return False
        return True
    

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            client_message_buffer = self.message_buffer[client.client_id]
            if len(client_message_buffer) != 0 and self.__is_causally_ready(client_message_buffer[0].operation):
                client_ids.append(client.client_id)
        
        return client_ids


    def _check_all_operations_causally_ordered(self, incoming_operation: GOTOperation) -> tuple[bool, int]:
            """
            Checks if the operations in the history buffer are ALL causally ordered before the incoming operation.
    
            Parameters
            ----------
            incoming_operation : Operation
                The operation to which causal order is checked.
    
            Returns
            -------
            1. `(False, first_independent_op_idx)` if there is an operation that is NOT causally ordered.
            2. `(True, -1)` otherwise.
            """
            all_operations_causally_ordered = True
    
            # Start from the left of the history buffer, and find the first element that is independent with respect
            # to the incoming operation
            first_independent_op_idx = 0
            for op in self._history_buffer:
                if not op.is_causally_ordered(incoming_operation):
                    all_operations_causally_ordered = False
                    break
    
                first_independent_op_idx += 1
    
            if all_operations_causally_ordered:
                return True, -1
    
            return False, first_independent_op_idx

    def _find_all_causally_ordered_operations_from(
            self, i: int, incoming_operation: GOTOperation
        ) -> list[tuple[int, GOTOperation]]:
            """
            Returns all operations in the history buffer (starting from index i) that are causally ordered with respect
            to the incoming operation
    
            Parameters
            ----------
            i : int
                The index of the first operation to start scanning from.
            incoming_operation : Operation
                The operation to which causal order is checked.
    
            Returns
            -------
            A list of all (j, self.history_buffer[j]) in the history buffer that are causally ordered with respect to the
            incoming operation.
            """
            causally_ordered_ops: list[tuple[int, GOTOperation]] = []
    
            for j in range(i, len(self._history_buffer)):
                if self._history_buffer[j].is_causally_ordered(incoming_operation):
                    causally_ordered_ops.append((j, self._history_buffer[j]))
    
            return causally_ordered_ops

    def _undo_non_totally_ordered_operations(self, incoming_operation: GOTOperation) -> list[GOTOperation]:
            """
            Start from the right of the history buffer and keep undo-ing operations until the most recent
            operation in the history buffer is totally ordered before the incoming operation.
    
            Returns the list of operations that were undone.
            """
            undone_operations : list[GOTOperation] = []
    
            for i in range(len(self._history_buffer) - 1, -1, -1):
                if self._history_buffer[i].is_totally_ordered(incoming_operation):
                    break
                else:
                    self._undo_operation(self._history_buffer[i])
                    undone_operations.append(self._pop_history_buffer())
    
            return undone_operations

    def _pop_history_buffer(self) -> GOTOperation:
            """
            Remove the last operation from the history buffer, and decrement the site state vector at index `op.client_id`.
            """
            op = self._history_buffer.pop()
            self.vector_clock[op.client_id] -= 1
            return op

    def _undo_operation(self, operation: GOTOperation):
            """
            Undo `operation` by first creating the inverse operation, and then applying the inverse operation to
            the current state.
            """
            undo_op: GOTOperation
    
            if isinstance(operation, GOTInsertOperation):
                undo_op = GOTDeleteOperation(
                    len(operation.sequence), operation.idx, operation.sequence, operation.client_id, operation.state_vector
                )
            elif isinstance(operation, GOTDeleteOperation):
                undo_op = GOTInsertOperation(operation.idx, operation.sequence, operation.client_id, operation.state_vector)
            else:
                raise ValueError("Unknown operation")
    
            self._apply_operation_to_document(undo_op, add_to_history_buffer=False, increment_state_vector=False)
         
    def _apply_operation_to_document(
            self, operation: GOTOperation, add_to_history_buffer: bool = True, increment_state_vector: bool = True
        ) -> None:
            """
            Perform an operation on the current document state.
    
            Parameters
            ----------
            operation : Operation
                The operation to be performed.
            add_to_history_buffer : bool
                Whether to add the operation to the history buffer.
                Pass `False` if the operation is an undo operation---we don't want to add the undone form of an already
                executed operation to the history buffer.
            increment_state_vector : bool
                Whether to increment the state vector at the index of the client that generated the operation.
            """
            if isinstance(operation, GOTSplitDeleteOperation):
                return self._apply_split_delete_operation_to_document(operation)
    
            if increment_state_vector:
                self.vector_clock[operation.client_id] += 1
    
            if add_to_history_buffer:
                self._history_buffer.append(operation)
    
            new_state = self._obtain_new_state(operation)
            self.state = new_state

    def _obtain_new_state(self, operation: GOTOperation) -> list[UniqueChar]:
            """
            Obtain the new state after applying `operation` to the current state.
            """
            if isinstance(operation, GOTInsertOperation):
                if len(operation.sequence) == 0:
                    return self.state
                new_state = self.state[: operation.idx] + operation.sequence + self.state[operation.idx :]
            elif isinstance(operation, GOTDeleteOperation):
                new_state = self.state[: operation.idx] + self.state[operation.idx + operation.num_to_delete :]
            else:
                raise ValueError("Unknown operation")
    
            return new_state

    def _apply_split_delete_operation_to_document(self, operation: GOTSplitDeleteOperation) -> None:
            """
            Applies a GOTSplitDeleteOperation by first flattening and transforming the GOTSplitDeleteOperation
            into a list of GOTDeleteOperations (via `_flatten_and_transform_split_operation`), and then applying each
            operation in the resulting list. The site state vector is only incremented once.
            """
            flattened_and_transformed = self._flatten_and_transform_split_operation(operation)
            for i, op in enumerate(flattened_and_transformed):
                self._apply_operation_to_document(
                    op, add_to_history_buffer=True, increment_state_vector=True if i == 0 else False
                )


    def _flatten_and_transform_split_operation(self, operation: GOTSplitDeleteOperation) -> list[GOTOperation]:
            """
            Flattens a GOTSplitDeleteOperation into a list of GOTDeleteOperations.
            - Since all operations in the resulting list are context-equivalent to one another, element i needs to be
              included against all preceding elements in the list, for i >= 1.
            - The resulting list of elements is returned.
            """
            return self.inclusion_transformer.include_split_deletes(operation)

    def _redo_undone_operations(self, undone_operations: list[GOTOperation], newly_performed: GOTOperation) -> None:
            """
            Redoes all operations in `undone_operations` as per the Undo/Do/Redo scheme of the GOT algorithm.
    
            Parameters
            ----------
            undone_operations : list[Operation]
                The list of operations that were undone.
            newly_performed : Operation
                The incoming operation that was just performed.
            """
            redone_ops: list[GOTOperation] = []
    
            if isinstance(newly_performed, GOTSplitDeleteOperation):
                transformed_newly_performed = self._flatten_and_transform_split_operation(newly_performed)
            else:
                transformed_newly_performed = [newly_performed]
    
            for key in range(len(undone_operations) - 1, -1, -1):
                undone_operation = undone_operations[key]
    
                if key == len(undone_operations) - 1:
                    op_to_redo = self.inclusion_transformer.list_inclusion_transform(
                        undone_operation, transformed_newly_performed
                    )
                else:
                    op_to_redo = self.inclusion_transformer.list_inclusion_transform(
                        self.exclusion_transformer.list_exclusion_transform(undone_operation, undone_operations[key + 1 :]),
                        transformed_newly_performed + redone_ops,
                    )
    
                if isinstance(op_to_redo, GOTSplitDeleteOperation):
                    transformed_chain = self._flatten_and_transform_split_operation(op_to_redo)
                    redone_ops.extend(transformed_chain)
                else:
                    redone_ops.append(op_to_redo)
                self._apply_operation_to_document(op_to_redo)
    