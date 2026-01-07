import asyncio
import os
from functions.alldebridFunctions import getDownloads as getAlldebridDownloads, getDownloadLink as getAlldebridDownloadLink
from functions.torboxFunctions import getDownloads as getTorboxDownloads, getDownloadLink as getTorboxDownloadLink
import logging
from library.tinfoil import errorMessage
from fastapi import BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
import fnmatch
import human_readable
import httpx
from urllib.parse import unquote
import time

PROVIDER = os.getenv("PROVIDER", "alldebrid").lower()

ACCEPTABLE_SWITCH_FILES = [".nsp", ".nsz", ".xci", ".xcz"]


async def getDownloads():
    if PROVIDER == "torbox":
        torrents = await getTorboxDownloads("torrents")
        usenet = await getTorboxDownloads("usenet")
        webdl = await getTorboxDownloads("webdl")
        return torrents + usenet + webdl
    else:
        return await getAlldebridDownloads()


async def generateIndex(base_url: str):
    """
    Generates a JSON index from your Alldebrid files. Matches only switch compatible files and returns a well-formatted JSON index for Tinfoil.

    Requires:
    - base_url: where the server is hosted, so it can create proper URLs.

    Returns:
    - dict: the generated index for Tinfoil to use.
    """

    success_message = "Welcome to your self-hosted Alldebrid/Torbox Tinfoil Server! You are now able to directly download your files to your switch.\n\n"
    files = []

    try:
        # Get all downloads from provider
        file_list = await getDownloads()

        for file in file_list:
            file_name = file.get("name", None)
            download_type = file.get("type")
            download_id = file.get("id")
            file_id = file.get("file_id", 0)

            for acceptable_file_type in ACCEPTABLE_SWITCH_FILES:
                if fnmatch.fnmatch(file_name.lower(), f"*{acceptable_file_type}"):
                    # create a url for the download
                    files.append(
                        {
                            # example base_url = http://192.168.0.1/
                            # example complete_url = http://192.168.0.1/magnets/123456/0#Game_Name
                            "url": f"{base_url}{download_type}/{download_id}/{file_id}#{file_name}",
                            "size": file.get("size", 0),
                        }
                    )

        success_message += f"Total Files: {len(files)}"
        success_message += f"\nTotal Size: {human_readable.file_size(sum([file.get('size', 0) for file in files]))}"
        return JSONResponse(
            status_code=200, content={"success": success_message, "files": files}
        )
    except Exception as e:
        logging.error(f"There was an error generating the index. Error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content=errorMessage(
                f"There was an error generating the index. Error: {str(e)}",
                error_code="UNKNOWN_ERROR",
            ),
        )


async def serveFile(
    request: Request,
    background_task: BackgroundTasks,
    download_type: str,
    download_id: str,
    file_id: str = "0",
):
    """
    Retrieves the Alldebrid download link and starts proxying the download through the server. This is necessary as generating a bunch of links through the index generation process can take some time, and is wasteful.

    Requires:
    - download_type: the download type of the file. Must be 'magnets'.
    - download_id: a string which represents the id of the magnet in Alldebrid.
    - file_id: an integer which represents the index of the file within the magnet.

    Returns:
    - Streaming Response: containing the download of the file to be served on the fly.
    """

    try:
        logging.info(f"Serving file: {download_type}/{download_id}/{file_id} via {PROVIDER}")
        
        if PROVIDER == "torbox":
            download_link = await getTorboxDownloadLink(download_type, download_id, int(file_id))
        else:
            download_link = await getAlldebridDownloadLink(download_id, int(file_id))

        if not download_link:
            return errorMessage("Unable to retrieve download link.")

        # Unquote the link because the provider might provide it encoded, and RedirectResponse re-encodes it.
        final_link = unquote(download_link)
        
        # Determine Proxy Mode
        # We check env var here to ensure it's loaded correctly at runtime
        USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
        logging.info(f"Config: USE_PROXY={USE_PROXY}")
        
        # PROXY MODE (For VPS users on Torbox, or local users who want speed logs)
        if USE_PROXY:
            logging.info("Proxy Mode Enabled. Streaming file through server...")
            client = httpx.AsyncClient()
            
            req_headers = {
                "User-Agent": request.headers.get("user-agent", "Mozilla/5.0"),
                "Range": request.headers.get("range"),
            }
            # Remove None headers
            req_headers = {k: v for k, v in req_headers.items() if v is not None}

            req_upstream = client.build_request("GET", final_link, headers=req_headers, timeout=None)
            response = await client.send(req_upstream, stream=True)
            
            # Check for errors from provider
            if response.status_code >= 400:
                logging.error(f"Provider returned error: {response.status_code}")
                await response.aclose()
                return errorMessage(f"Provider Error: {response.status_code}")

            cleanup = background_task.add_task(response.aclose)
            
            res_headers = {
                "Accept-Ranges": "bytes",
                "Content-Type": response.headers.get("Content-Type", "application/octet-stream"),
                "Content-Length": response.headers.get("Content-Length"),
                "Content-Range": response.headers.get("Content-Range"),
                "Content-Disposition": f'attachment; filename="{final_link.split("/")[-1]}"',
            }
            # Remove None headers
            res_headers = {k: v for k, v in res_headers.items() if v is not None}

            async def speed_iterator(iterator):
                start_time = time.time()
                last_log_time = start_time
                bytes_since_last_log = 0
                try:
                    async for chunk in iterator:
                        yield chunk
                        bytes_since_last_log += len(chunk)
                        current_time = time.time()
                        if current_time - last_log_time >= 5:
                            interval = current_time - last_log_time
                            speed = (bytes_since_last_log / 1024 / 1024) / interval
                            logging.info(f"Serving speed: {speed:.2f} MB/s")
                            last_log_time = current_time
                            bytes_since_last_log = 0
                except Exception as e:
                    logging.error(f"Stream error: {e}")
                    raise e

            return StreamingResponse(
                content=speed_iterator(response.aiter_bytes(chunk_size=1024 * 1024 * 4)),
                status_code=response.status_code,
                headers=res_headers,
                background=cleanup
            )


        # REDIRECT MODE (Default for Alldebrid/Local)
        # Check if VPS is blocked (Pre-flight check)
        try:
            async with httpx.AsyncClient() as client:
                headers = {"User-Agent": "Mozilla/5.0 (Nintendo Switch; WifiWebAuthApplet)"}
                check = await client.head(final_link, headers=headers, follow_redirects=True, timeout=3.0)
                
                if check.status_code == 503:
                    logging.error(f"ALERT: VPS IS BLOCKED BY {PROVIDER.upper()} (503 Service Unavailable).")
                    logging.error("Your VPS IP address is blacklisted. USE_PROXY=true might help for Torbox, but not Alldebrid.")
                elif check.status_code == 403:
                    logging.error("ALERT: LINK FORBIDDEN (403 Forbidden).")
                    logging.error("Possible IP Locking. Try enabling USE_PROXY=true (if Provider allows VPS).")
                elif check.status_code != 200 and check.status_code != 206:
                    logging.warning(f"Warning: {PROVIDER} returned code {check.status_code} during connectivity check.")
                    
        except Exception as e:
            logging.warning(f"Unable to verify {PROVIDER} link status: {e}")

        # Use 307 Temporary Redirect to force Tinfoil to preserve the 'Range' header.
        return RedirectResponse(url=final_link, status_code=307)
        
    except Exception as e:
        logging.error(f"Error serving file: {e}")
        return errorMessage("Internal Server Error")
