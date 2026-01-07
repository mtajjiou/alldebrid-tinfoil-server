import asyncio
from functions.alldebridFunctions import getDownloads, getDownloadLink
import logging
from library.tinfoil import errorMessage
from fastapi import BackgroundTasks, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
import fnmatch
import human_readable

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
    # Redirect Mode with Double-Encoding Fix
    # VPS (Coolify) is blocked by Alldebrid (503), so we MUST use Redirects.
    # We unquote the URL to prevent FastAPI from double-encoding it (e.g. %20 -> %2520), which breaks the link.
    
    # Log Debug Info
    logging.info(f"ServeFile: Redirecting to {download_link}")
    logging.info(f"Request Headers: {request.headers}")
    
    from urllib.parse import unquote
    from fastapi.responses import RedirectResponse
    
    # Unquote the link because Alldebrid provides it encoded, and RedirectResponse re-encodes it.
    final_link = unquote(download_link)
    
    # Use 307 Temporary Redirect to force Tinfoil to preserve the 'Range' header.
    # A standard 302 might cause Tinfoil to drop headers and request the full file (failing the open).
    return RedirectResponse(url=final_link, status_code=307)
