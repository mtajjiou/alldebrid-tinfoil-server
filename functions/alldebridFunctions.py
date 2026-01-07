import httpx
from library.alldebrid import ALLDEBRID_API_KEY, ALLDEBRID_API_URL
import logging
import traceback
from typing import Optional


async def getReadyMagnets() -> list:
    """
    Gets all ready magnets from Alldebrid.

    Returns:
    - list: a list of magnet objects that are ready (statusCode=4).
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{ALLDEBRID_API_URL}.1/magnet/status",
                headers={
                    "Authorization": f"Bearer {ALLDEBRID_API_KEY}",
                },
                data={"status": "ready"},
            )

        if response.status_code != httpx.codes.OK:
            logging.error(
                f"Unable to retrieve Alldebrid magnets. Response Code: {response.status_code}. Response: {response.text}"
            )
            return []

        json_response = response.json()
        logging.info(f"Alldebrid magnet/status response: {json_response}")
        
        if json_response.get("status") != "success":
            error = json_response.get("error", {})
            logging.error(
                f"Alldebrid API error: {error.get('code')} - {error.get('message')}"
            )
            return []

        data = json_response.get("data", {})
        magnets = data.get("magnets", {})
        
        # Log what we received
        logging.info(f"Retrieved {len(magnets)} ready magnets from Alldebrid")
        
        # Handle case where magnets is a dict (with string keys like "0", "1", etc.)
        if isinstance(magnets, dict):
            magnets = list(magnets.values())
        
        # Handle case where magnets might be a single magnet dict (not in a list)
        if isinstance(magnets, dict) and "id" in magnets:
            magnets = [magnets]
        
        # Ensure each item is a dict (not a string)
        valid_magnets = []
        for m in magnets:
            if isinstance(m, dict):
                valid_magnets.append(m)
            else:
                logging.warning(f"Unexpected magnet format: {type(m)} - {m}")
        
        return valid_magnets

    except Exception as e:
        traceback.print_exc()
        logging.error(f"There was an error getting magnets from Alldebrid. Error: {str(e)}")
        return []


async def getMagnetFiles(magnet_ids: list) -> dict:
    """
    Gets file details for specific magnets from Alldebrid.

    Requires:
    - magnet_ids: list of magnet IDs to get files for.

    Returns:
    - dict: mapping of magnet_id to file list.
    """
    if not magnet_ids:
        return {}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{ALLDEBRID_API_URL}/magnet/files",
                headers={
                    "Authorization": f"Bearer {ALLDEBRID_API_KEY}",
                },
                data={"id[]": magnet_ids},
            )

        if response.status_code != httpx.codes.OK:
            logging.error(
                f"Unable to retrieve Alldebrid magnet files. Response Code: {response.status_code}. Response: {response.text}"
            )
            return {}

        json_response = response.json()
        if json_response.get("status") != "success":
            error = json_response.get("error", {})
            logging.error(
                f"Alldebrid API error: {error.get('code')} - {error.get('message')}"
            )
            return {}

        magnets = json_response.get("data", {}).get("magnets", [])
        result = {}
        for magnet in magnets:
            magnet_id = magnet.get("id")
            if "error" not in magnet:
                result[str(magnet_id)] = magnet.get("files", [])

        return result

    except Exception as e:
        traceback.print_exc()
        logging.error(f"There was an error getting magnet files from Alldebrid. Error: {str(e)}")
        return {}


def flattenFiles(files: list, path_prefix: str = "") -> list:
    """
    Flattens the nested file structure from Alldebrid into a simple list.

    Alldebrid returns files in a nested structure where:
    - 'n' = filename or folder name
    - 's' = size (only for files)
    - 'l' = link (only for files)
    - 'e' = entries (only for folders, contains nested files)

    Returns:
    - list: flattened list of files with name, size, and link.
    """
    result = []
    for idx, item in enumerate(files):
        name = item.get("n", "")
        
        if "e" in item:
            # This is a folder, recurse into it
            nested = flattenFiles(item["e"], f"{path_prefix}{name}/")
            result.extend(nested)
        elif "l" in item:
            # This is a file with a download link
            result.append({
                "name": name,
                "full_path": f"{path_prefix}{name}",
                "size": item.get("s", 0),
                "link": item.get("l"),
                "index": len(result),
            })
    
    return result


async def unlockLink(link: str) -> Optional[str]:
    """
    Unlocks an Alldebrid link to get the actual download URL.

    Requires:
    - link: the Alldebrid file link (e.g., https://alldebrid.com/f/xxxxx)

    Returns:
    - str: the actual download URL, or None if failed.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{ALLDEBRID_API_URL}/link/unlock",
                headers={
                    "Authorization": f"Bearer {ALLDEBRID_API_KEY}",
                },
                data={"link": link},
            )

        if response.status_code != httpx.codes.OK:
            logging.error(
                f"Unable to unlock Alldebrid link. Response Code: {response.status_code}. Response: {response.text}"
            )
            return None

        json_response = response.json()
        if json_response.get("status") != "success":
            error = json_response.get("error", {})
            logging.error(
                f"Alldebrid API error: {error.get('code')} - {error.get('message')}"
            )
            return None

        # Check if it's a delayed link
        data = json_response.get("data", {})
        if "delayed" in data:
            # Need to poll for the link
            delayed_id = data["delayed"]
            return await waitForDelayedLink(delayed_id)

        return data.get("link")

    except Exception as e:
        traceback.print_exc()
        logging.error(f"There was an error unlocking link from Alldebrid. Error: {str(e)}")
        return None


async def waitForDelayedLink(delayed_id: int, max_attempts: int = 60) -> Optional[str]:
    """
    Polls the delayed link endpoint until the download link is ready.

    Requires:
    - delayed_id: the delayed ID from the unlock response.
    - max_attempts: maximum number of polling attempts (default 60, ~5 minutes).

    Returns:
    - str: the actual download URL, or None if failed/timeout.
    """
    import asyncio

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url=f"{ALLDEBRID_API_URL}/link/delayed",
                    headers={
                        "Authorization": f"Bearer {ALLDEBRID_API_KEY}",
                    },
                    data={"id": delayed_id},
                )

            if response.status_code != httpx.codes.OK:
                logging.warning(f"Delayed link check failed, attempt {attempt + 1}")
                await asyncio.sleep(5)
                continue

            json_response = response.json()
            if json_response.get("status") != "success":
                await asyncio.sleep(5)
                continue

            data = json_response.get("data", {})
            status = data.get("status", 0)

            if status == 2:  # Ready
                return data.get("link")
            elif status == 3:  # Error
                logging.error("Delayed link generation failed")
                return None
            else:  # Still processing
                await asyncio.sleep(5)

        except Exception as e:
            logging.warning(f"Error checking delayed link: {str(e)}")
            await asyncio.sleep(5)

    logging.error("Timeout waiting for delayed link")
    return None


# Cache to store file mappings for serving
_file_cache: dict = {}


async def getDownloads() -> list:
    """
    Gets all downloadable files from ready Alldebrid magnets.

    Returns:
    - file_list: a list containing all of the files retrieved from the Alldebrid API.
    """
    global _file_cache

    try:
        # Get all ready magnets
        magnets = await getReadyMagnets()
        if not magnets:
            return []

        # Get magnet IDs
        magnet_ids = [m.get("id") for m in magnets if m.get("id")]

        # Get files for all magnets
        magnet_files = await getMagnetFiles(magnet_ids)

        files = []
        _file_cache = {}  # Reset cache

        for magnet_id, magnet_file_list in magnet_files.items():
            # Flatten the nested file structure
            flat_files = flattenFiles(magnet_file_list)

            for idx, file_info in enumerate(flat_files):
                file_entry = {
                    "type": "magnets",
                    "id": magnet_id,
                    "file_id": idx,
                    "name": file_info["name"],
                    "size": file_info["size"],
                    "link": file_info["link"],
                }
                files.append(file_entry)

                # Cache the link for later serving
                cache_key = f"{magnet_id}_{idx}"
                _file_cache[cache_key] = file_info["link"]

        return files

    except Exception as e:
        traceback.print_exc()
        logging.error(f"There was an error getting downloads from Alldebrid. Error: {str(e)}")
        return []


async def getDownloadLink(magnet_id: str, file_id: int) -> Optional[str]:
    """
    Gets the download link for a specific file from a magnet.

    Requires:
    - magnet_id: the magnet ID.
    - file_id: the file index within the magnet.

    Returns:
    - str: the actual download URL, or None if failed.
    """
    global _file_cache

    cache_key = f"{magnet_id}_{file_id}"

    # First check cache
    if cache_key in _file_cache:
        alldebrid_link = _file_cache[cache_key]
    else:
        # Need to fetch the file info
        magnet_files = await getMagnetFiles([magnet_id])
        if magnet_id not in magnet_files:
            logging.error(f"Could not find magnet {magnet_id}")
            return None

        flat_files = flattenFiles(magnet_files[magnet_id])
        if file_id >= len(flat_files):
            logging.error(f"File index {file_id} out of range for magnet {magnet_id}")
            return None

        alldebrid_link = flat_files[file_id]["link"]
        _file_cache[cache_key] = alldebrid_link

    # Unlock the link to get the actual download URL
    return await unlockLink(alldebrid_link)
