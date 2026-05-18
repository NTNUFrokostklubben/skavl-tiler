import shutil
import threading
from pathlib import Path

from skavl_proto import shutdown_pb2_grpc, shutdown_pb2

class ShutdownServicer(shutdown_pb2_grpc.ShutdownServiceServicer):
    """
    Servicer to handle graceful shutdown from remote endpoints
    """
    def __init__(self, server, cache_root: Path):
        self._server = server
        self._cache_root = cache_root

    def Shutdown(self, request, context):
        """
        Shuts down server and deletes local tilecache.
        Args:
            request:
            context:

        Returns:

        """
        print("shutdown received", flush=True)
        shutil.rmtree(self._cache_root, ignore_errors=True)
        print(f"tilecache deleted: {self._cache_root}", flush=True)
        threading.Timer(0.2, self._server.stop, args=[2]).start()
        return shutdown_pb2.ShutdownResponse()