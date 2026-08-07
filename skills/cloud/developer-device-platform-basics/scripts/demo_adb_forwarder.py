"""Demo client that forwards ADB traffic to/from remote device sessions.

This script uses the Devicestreaming API's `adb_connect` method to set up
a bidirectional gRPC stream for forwarding ADB traffic.

For the API definition, see:
https://docs.cloud.google.com/python/docs/reference/google-cloud-devicestreaming/latest/google.cloud.devicestreaming_v1.services.direct_access_service.DirectAccessServiceAsyncClient#google_cloud_devicestreaming_v1_services_direct_access_service_DirectAccessServiceAsyncClient_adb_connect
"""

import asyncio
from collections.abc import AsyncIterator, Sequence
import struct
import sys
from typing import Any

from absl import app
from absl import flags
from absl import logging
from google.api_core import client_options
from google.cloud import devicestreaming_v1
from google.oauth2 import credentials
import grpc

# https://android.googlesource.com/platform/system/adb/+/refs/heads/main/protocol.txt
CNXN = 0x4E584E43
OPEN = 0x4E45504F
OKAY = 0x59414B4F
CLSE = 0x45534C43
WRTE = 0x45545257

_DEFAULT_STREAM_ID = 1000
_TIMEOUT_BUFFER_SECONDS = 10


async def send_packet(
    writer: asyncio.StreamWriter,
    cmd: int,
    arg0: int,
    arg1: int,
    payload: bytes = b"",
) -> None:
  """Sends an ADB packet over the writer.

  Args:
    writer: The stream writer to send the packet to.
    cmd: The ADB command constant (e.g., CNXN, OPEN).
    arg0: The first argument of the ADB command.
    arg1: The second argument of the ADB command.
    payload: The optional payload data.
  """
  magic = cmd ^ 0xFFFFFFFF
  header = struct.pack("<6I", cmd, arg0, arg1, len(payload), 0, magic)
  writer.write(header + payload)
  await writer.drain()


class AdbForwarder:
  """Forwarder that forwards ADB traffic to/from a remote device session."""

  def __init__(
      self,
      resource_name: str,
      access_token: str | None = None,
      endpoint: str = "devicestreaming.googleapis.com",
      timeout: float | None = None,
  ):
    """Initializes the AdbForwarder instance."""
    self.resource_name = resource_name
    self.access_token = access_token
    self.endpoint = endpoint
    self.requests_queue: asyncio.Queue[devicestreaming_v1.AdbMessage | None] = (
        asyncio.Queue(maxsize=128)
    )
    self.active_writer: asyncio.StreamWriter | None = None
    self.features = "cmd,stat,shell_v2"
    self.server: asyncio.AbstractServer | None = None
    self.port: int | None = None
    self.stream_writers: dict[int, asyncio.StreamWriter] = {}
    self.grpc_client: (
        devicestreaming_v1.DirectAccessServiceAsyncClient | None
    ) = None
    self.grpc_call: Any | None = None
    self.timeout = timeout
    self.running = True
    self.receive_task: asyncio.Task[None] | None = None

    # Parse project and session_id from resource_name
    parts = resource_name.split("/")
    if (
        len(parts) != 4
        or parts[0] != "projects"
        or parts[2] != "deviceSessions"
    ):
      raise ValueError(
          "Invalid resource_name format. Expected"
          " projects/<project>/deviceSessions/<session-id>"
      )
    _, self.project, _, self.session_id = parts

  async def start(self) -> None:
    """Starts the ADB forwarder."""
    self.server = await asyncio.start_server(
        self.client_connected, "127.0.0.1", 0
    )
    self.port = self.server.sockets[0].getsockname()[1]
    logging.info("Connecting to device session %s...", self.session_id)
    logging.info("Waiting for device...")

    # Set up credentials and client options for public devicestreaming client
    creds = (
        credentials.Credentials(self.access_token)
        if self.access_token
        else None
    )
    options = client_options.ClientOptions(api_endpoint=self.endpoint)
    self.grpc_client = devicestreaming_v1.DirectAccessServiceAsyncClient(
        credentials=creds,
        client_options=options,
    )

    metadata = [
        ("x-omnilab-session-name", self.resource_name),
        ("x-goog-user-project", self.project),
    ]

    initial_msg = devicestreaming_v1.AdbMessage(
        # Set default stream_id to avoid conflict ADB channels.
        open_=devicestreaming_v1.Open(
            stream_id=_DEFAULT_STREAM_ID,
            service="shell:echo 'Establishing a connection'",
        )
    )
    await self.requests_queue.put(initial_msg)

    self.grpc_call = await self.grpc_client.adb_connect(
        requests=self.request_generator(),
        metadata=metadata,
        timeout=self.timeout,
    )
    self.receive_task = asyncio.create_task(self.receive_grpc_messages())

    logging.info(
        "Device connected successfully! ADB forwarding listening on"
        " localhost:%s",
        self.port,
    )
    logging.info("Press Ctrl+C to disconnect and exit.")

    try:
      proc = await asyncio.create_subprocess_exec(
          "adb",
          "connect",
          f"localhost:{self.port}",
      )
      await proc.wait()
    except OSError as e:
      logging.warning("Failed to run adb connect: %s", e)

  async def request_generator(
      self,
  ) -> AsyncIterator[devicestreaming_v1.AdbMessage]:
    """Generates requests for the gRPC stream."""
    while self.running:
      if (msg := await self.requests_queue.get()) is None:
        break
      yield msg

  async def client_connected(
      self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
  ) -> None:
    """Handles a new local ADB client connection.

    Args:
      reader: The stream reader for the local client.
      writer: The stream writer for the local client.
    """
    peer = writer.get_extra_info("peername")
    logging.info("[AdbForwarder] Client connected: %s", peer)
    self.active_writer = writer
    try:
      while self.running:
        header = await reader.readexactly(24)
        cmd, arg0, arg1, length, _, _ = struct.unpack("<6I", header)
        payload = await reader.readexactly(length) if length > 0 else b""

        if cmd == CNXN:
          feat = self.features.encode("utf-8")
          payload = b"device::features=" + feat
          await send_packet(writer, CNXN, 0x01000001, 1024 * 1024, payload)
        elif cmd == OPEN:
          local_id = arg0
          service = payload.decode("utf-8", errors="ignore")
          logging.info(
              "[AdbForwarder] OPEN request for service: %s",
              service.replace(chr(0), ""),
          )
          if service.startswith("reverse:"):
            await self.reject_reverse(writer, local_id)
            continue

          msg = devicestreaming_v1.AdbMessage(
              open_=devicestreaming_v1.Open(stream_id=local_id, service=service)
          )
          self.stream_writers[local_id] = writer
          await self.requests_queue.put(msg)

        elif cmd == WRTE:
          local_id = arg0
          remote_id = arg1
          self.stream_writers[remote_id] = writer
          msg = devicestreaming_v1.AdbMessage(
              stream_data=devicestreaming_v1.StreamData(
                  stream_id=remote_id, data=payload
              )
          )
          await self.requests_queue.put(msg)
          await send_packet(writer, OKAY, remote_id, local_id)
        elif cmd == OKAY:
          pass
        elif cmd == CLSE:
          remote_id = arg1
          msg = devicestreaming_v1.AdbMessage(
              stream_data=devicestreaming_v1.StreamData(
                  stream_id=remote_id, close=devicestreaming_v1.Close()
              )
          )
          await self.requests_queue.put(msg)
    except asyncio.IncompleteReadError:
      pass
    except OSError:
      logging.exception("Client connection error")
    finally:
      logging.info("[AdbForwarder] Client disconnected: %s", peer)
      writer.close()
      await writer.wait_closed()

  async def receive_grpc_messages(self) -> None:
    """Receives messages from the gRPC stream and forwards them to clients."""
    logging.info("[AdbForwarder] Starting receive_grpc_messages")
    grpc_call = self.grpc_call
    if not grpc_call:
      logging.error("[AdbForwarder] grpc_call is None")
      return
    try:
      async for msg in grpc_call:
        device_msg = msg
        assert device_msg is not None
        content_type = type(device_msg).pb(device_msg).WhichOneof("contents")

        if not self.active_writer:
          logging.warning(
              "[AdbForwarder] gRPC msg %s received but no active writer",
              content_type,
          )
          continue
        if content_type == "status_update":
          self.features = device_msg.status_update.features
        elif content_type == "stream_status":
          stream_id = device_msg.stream_status.stream_id
          writer = self.stream_writers.get(stream_id, self.active_writer)
          await send_packet(writer, OKAY, stream_id, stream_id)
        elif content_type == "stream_data":
          stream_data = device_msg.stream_data
          stream_id = stream_data.stream_id
          data_type = type(stream_data).pb(stream_data).WhichOneof("contents")
          writer = self.stream_writers.get(stream_id, self.active_writer)
          if data_type == "data":
            data = stream_data.data
            await send_packet(writer, WRTE, stream_id, stream_id, data)
          elif data_type == "close":
            await send_packet(writer, CLSE, stream_id, stream_id)
    except asyncio.CancelledError:
      pass
    except grpc.RpcError:
      logging.exception("gRPC receiving error")

  async def reject_reverse(
      self, writer: asyncio.StreamWriter, local_id: int
  ) -> None:
    """Rejects a reverse port forwarding request from the client.

    Args:
      writer: The stream writer to send the rejection packet to.
      local_id: The local ID of the stream requesting reverse forwarding.
    """
    await send_packet(writer, OKAY, local_id, local_id)
    reason = "reverse forwarding not supported"
    fail_str = f"FAIL{len(reason):04X}{reason}".encode("utf-8")
    await send_packet(writer, WRTE, local_id, local_id, fail_str)
    await send_packet(writer, CLSE, local_id, local_id)

  async def stop(self) -> None:
    """Stops the ADB forwarder and cleans up resources."""
    logging.info("[AdbForwarder] Stopping...")
    self.running = False
    if self.port:
      try:
        proc = await asyncio.create_subprocess_exec(
            "adb",
            "disconnect",
            f"localhost:{self.port}",
        )
        await proc.wait()
      except OSError as e:
        logging.warning("Failed to run adb disconnect: %s", e)
    await self.requests_queue.put(None)
    if self.server:
      self.server.close()
      await self.server.wait_closed()
    if self.grpc_client:
      try:
        await self.grpc_client.transport.close()
      except (grpc.RpcError, RuntimeError):
        pass
    logging.info("[AdbForwarder] Stopped")


_DEVICE_SESSION = flags.DEFINE_string(
    "device_session", None, "Full resource name of the device session"
)
_ACCESS_TOKEN = flags.DEFINE_string("access_token", None, "OAuth2 access token")
_TTL = flags.DEFINE_integer(
    "ttl",
    900,
    "Time to live (in seconds) for the forwarder.",
)


def main(argv: Sequence[str]) -> None:
  """Main entry point."""
  del argv
  if not _DEVICE_SESSION.value:
    logging.error("Missing --device_session flag.")
    sys.exit(1)

  if _TTL.value is None or _TTL.value <= 0:
    logging.error("The --ttl flag must be a positive integer.")
    sys.exit(1)

  async def run_forwarder():
    # Set timeout to TTL + buffer for client side cleanup
    forwarder = AdbForwarder(
        _DEVICE_SESSION.value,
        _ACCESS_TOKEN.value,
        timeout=float(_TTL.value + _TIMEOUT_BUFFER_SECONDS),
    )
    await forwarder.start()
    try:
      logging.info("Forwarding will stop after %d seconds.", _TTL.value)

      assert forwarder.receive_task is not None
      await asyncio.wait_for(forwarder.receive_task, timeout=_TTL.value)
      logging.info("gRPC stream stopped. Stopping forwarder...")

    except asyncio.TimeoutError:
      logging.info(
          "Time to live of %d seconds reached. Stopping forwarder...",
          _TTL.value,
      )
    except (KeyboardInterrupt, asyncio.CancelledError):
      logging.info("Disconnecting...")
    finally:
      await forwarder.stop()

  try:
    asyncio.run(run_forwarder())
  except KeyboardInterrupt:
    pass


if __name__ == "__main__":
  app.run(main)
