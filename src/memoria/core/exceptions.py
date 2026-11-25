class MemoriaError(Exception):
    """Base class for domain errors raised by the service layer."""


class MemoryNotFoundError(MemoriaError):
    def __init__(self, memory_id: str, namespace: str):
        self.memory_id = memory_id
        self.namespace = namespace
        super().__init__(f"Memory with id {memory_id} not found in namespace '{namespace}'")
