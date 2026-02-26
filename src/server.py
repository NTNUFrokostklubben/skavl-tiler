from concurrent import futures
import random
import time

import grpc

from skavl_proto import progress_pb2
from skavl_proto import progress_pb2_grpc


class ProgressService(progress_pb2_grpc.ProgressServiceServicer):
    def GetProgress(self, request, context):
        # Dummy data for testing
        return progress_pb2.ProgressReport(
            project_name="dummy_project",
            progress=random.random(),
        )


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    progress_pb2_grpc.add_ProgressServiceServicer_to_server(ProgressService(), server)
    server.add_insecure_port("0.0.0.0:50051")
    server.start()
    print("gRPC server listening on 0.0.0.0:50051")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()