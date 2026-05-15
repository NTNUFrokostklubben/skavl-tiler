import argparse
from concurrent import futures
import random
import time


import grpc
from osgeo import gdal

from services.shutdown_servicer.shutdown_servicer import ShutdownServicer
from skavl_proto import progress_pb2, shutdown_pb2_grpc
from skavl_proto import progress_pb2_grpc
from skavl_proto import tiler_pb2_grpc
from services.tiler_servicer.tiler_servicer import TileServiceServicer


class ProgressService(progress_pb2_grpc.ProgressServiceServicer):
    def GetProgress(self, request, context):
        # Dummy data for testing
        return progress_pb2.ProgressReport(
            project_name="dummy_project",
            progress=random.random(),
        )

def serve():
    parser = argparse.ArgumentParser(
        prog="skavl-anomaly-detection-module",
        description="Anomaly detection in aerial images")

    parser.add_argument("-p", "--port", help="Port to start tiler server with", default=50051)
    parser.add_argument("-l", "--local", action="store_true",
                        help="""Determines if all or only local connections should be accepted. 
                                   If this argument is present, the servers IP will be 127.0.0.1, 
                                   if this argument is omitted, the ip will be set to 0.0.0.0 meaning accept all connections""")

    args = parser.parse_args()

    gdal.UseExceptions()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    progress_pb2_grpc.add_ProgressServiceServicer_to_server(ProgressService(), server)
    tiler_pb2_grpc.add_TilerServiceServicer_to_server(TileServiceServicer(), server)
    shutdown_pb2_grpc.add_ShutdownServiceServicer_to_server(ShutdownServicer(server), server)

    # Accepts connections only locally when running locally.
    server_port = getattr(args, "port")
    server_ip = ""
    if getattr(args, "local", False):
        server_ip = "127.0.0.1"
    else:
        server_ip = "0.0.0.0"
    server.add_insecure_port(f"{server_ip}:{server_port}")
    server.start()
    print(f"gRPC server listening on {server_ip}:{server_port}")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()