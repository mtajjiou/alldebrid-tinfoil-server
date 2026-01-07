import asyncio
import time
from functions.alldebridFunctions import getDownloads, getDownloadLink
import logging
from library.tinfoil import errorMessage
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
import fnmatch
import human_readable
import httpx

ACCEPTABLE_SWITCH_FILES = [".nsp", ".nsz", ".xci", ".xcz"]


async def generateIndex(base_url: str):
    """
    Generates a JSON index from your Alldebrid files. Matches only switch compatible files and returns a well-formatted JSON index for Tinfoil.

    Requires:
    - base_url: where the server is hosted, so it can create proper URLs.

    Returns:
    - dict: the generated index for Tinfoil to use.
    """

    success_message = "Welcome to your self-hosted Alldebrid Tinfoil Server! You are now able to directly download your files from Alldebrid to your switch.\n\n"
    files = []

    try:
        # Get all downloads from Alldebrid magnets
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
    file_id: int = 0,
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

    if download_type != "magnets":
        return JSONResponse(
            status_code=400,
            content=errorMessage(
                "Invalid download type. Only 'magnets' is supported.",
                error_code="INVALID_TYPE",
            ),
        )

    download_link = await getDownloadLink(
        magnet_id=download_id, file_id=file_id
    )

    if not download_link:
        return JSONResponse(
            status_code=500,
            content=errorMessage(
                "There was an error retrieving the download link from Alldebrid. Please try again.",
                error_code="DATABASE_ERROR",
            ),
        )

    # now stream link and stream out
    # Reverting to Proxy mode because Tinfoil fails to follow 302 Redirects for valid NSP metadata parsing.
    # Optimization: Using larger chunk size (512KB) to improve throughput and prevent 0.0MB/s stalls.
    
    client = httpx.AsyncClient()
    
    # Forward Range header if present
    req_headers = {}
    if "range" in request.headers:
        req_headers["Range"] = request.headers["range"]

    # Use a longer timeout for the download stream
    req_upstream = client.build_request(method="GET", url=download_link, headers=req_headers, timeout=None)
    response = await client.send(req_upstream, stream=True)

    cleanup = background_task.add_task(response.aclose)
    
    # Prepare response headers
    res_headers = {
        "Accept-Ranges": "bytes",
        "Content-Type": response.headers.get("Content-Type", "application/octet-stream"),
    }
    
    # Forward critical headers
    for header in ["Content-Length", "Content-Range", "Content-Disposition"]:
        if header in response.headers:
            res_headers[header] = response.headers[header]

    # Wrapper to log speed
    async def speed_iterator(iterator):
        start_time = time.time()
        last_log_time = start_time
        bytes_since_last_log = 0
        
        try:
            async for chunk in iterator:
                yield chunk
                bytes_since_last_log += len(chunk)
                current_time = time.time()
                
                # Log usage every 5 seconds
                if current_time - last_log_time >= 5:
                    interval = current_time - last_log_time
                    speed = (bytes_since_last_log / 1024 / 1024) / interval
                    logging.info(f"Serving file... Speed: {speed:.2f} MB/s")
                    
                    last_log_time = current_time
                    bytes_since_last_log = 0
        except Exception as e:
            logging.error(f"Stream error: {e}")
            raise e

    return StreamingResponse(
        content=speed_iterator(response.aiter_bytes(chunk_size=512 * 1024)), # 512KB chunks
        status_code=response.status_code,
        headers=res_headers,
        background=cleanup
    )
