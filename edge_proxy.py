"""Edge proxy: 172.19.0.1:3110 -> 127.0.0.1:3110.

Caddy-edge (docker, jaringan bridge) tidak bisa mencapai 127.0.0.1 host.
fund2-api wajib tetap bind 127.0.0.1 (PRD 7: endpoint EA lokal), dan EA
menembak http://127.0.0.1:3110/bridge langsung. Proxy ini hanya membuka
jalur docker-bridge -> host untuk Caddy, tidak mengubah bind API.
"""
import asyncio

LISTEN = ("172.19.0.1", 3110)
UPSTREAM = ("127.0.0.1", 3110)


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(client_reader, client_writer):
    try:
        up_reader, up_writer = await asyncio.open_connection(*UPSTREAM)
    except Exception:
        client_writer.close()
        return
    await asyncio.gather(
        pipe(client_reader, up_writer),
        pipe(up_reader, client_writer),
    )


async def main():
    server = await asyncio.start_server(handle, *LISTEN)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
