import json
import requests
import os
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.ttk import Combobox
from collections import Counter
from urllib.parse import urlparse
import logging

# Configure logging for debugging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

def setup_debug_logging():
    # Configure logging to write to a file
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("debug.log"),
            logging.StreamHandler()  # Logs to the console if available
        ]
    )
    logging.debug("Debug logging initialized.")

# Function to download a mod file from a given URL and save it to a specified path
# Metadata is added to the file for additional information
def download_mod(download_url, save_path, metadata):
    retries = 3  # Number of retry attempts for network issues
    for attempt in range(retries):
        try:
            # Send a GET request to the URL with a timeout
            response = requests.get(download_url, stream=True, timeout=10)
            response.raise_for_status()  # Raise an error for unsuccessful status codes
            with open(save_path, "wb") as file:
                # Write the content of the file in chunks to handle large files
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            # Save metadata
            metadata_path = f"{save_path}.meta.json"
            with open(metadata_path, "w") as meta_file:
                json.dump(metadata, meta_file, indent=4)
            logging.debug(f"Downloaded file saved to: {save_path}, metadata saved to: {metadata_path}")
            return  # Exit the function if download succeeds
        except requests.exceptions.ConnectionError:
            logging.error("Network connection error during download.")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise Exception("Network connection error while trying to download the file.")
        except requests.exceptions.Timeout:
            logging.error("Timeout occurred during download.")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise Exception("The request timed out while trying to download the file.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Request exception during download: {e}")
            raise Exception(f"An error occurred during the request: {e}")

# Function to retrieve the download URL of a mod from the Modrinth API
# Returns the URL, version information, and other metadata
def get_download_url_modrinth(mod_name, mod_loader, mc_version):
    base_url = "https://api.modrinth.com/v2"
    search_url = f"{base_url}/search"
    query_params = {
        "query": mod_name,
        "facets": f"[[\"categories:{mod_loader}\", \"versions:{mc_version}\"]]"
    }
    try:
        # Search for the mod using the Modrinth API
        response = requests.get(search_url, params=query_params, timeout=10)
        response.raise_for_status()
        results = response.json()["hits"]
        if not results:
            logging.debug(f"No matching mod found for: {mod_name}")
            return None, "No matching mod found.", None
        # Get the project ID and retrieve version details
        project_id = results[0]["project_id"]
        versions_url = f"{base_url}/project/{project_id}/version"
        version_response = requests.get(versions_url, timeout=10)
        version_response.raise_for_status()
        versions = version_response.json()
        for version in versions:
            # Filter for compatible mod loader and Minecraft version
            if mod_loader in version["loaders"] and mc_version in version["game_versions"]:
                file_url = version["files"][0]["url"]
                metadata = {
                    "version_number": version["version_number"],
                    "mod_loader": mod_loader,
                    "minecraft_version": mc_version
                }
                return file_url, None, metadata
        logging.debug(f"No compatible version found for mod: {mod_name}")
        return None, "No compatible version found.", None
    except requests.RequestException as e:
        logging.error(f"Error fetching mod details: {e}")
        return None, str(e), None

# Function to save the list of failed downloads to a log file
def save_failed_downloads(failed_downloads, save_directory):
    failed_log = os.path.join(save_directory, "failed_downloads.log")
    with open(failed_log, "w") as log:
        for failure in failed_downloads:
            log.write(f"Mod: {failure['name']}, Reason: {failure['reason']}\n")
    logging.debug(f"Failed downloads logged to: {failed_log}")
    return failed_log

# Main function to manage the downloading process
def start_download(json_path, save_directory, mod_loader, mc_version, log_area, progress_bar):
    failed_downloads = []
    start_time = time.time()  # Record the start time of the process

    def log_message(message):
        # Add a message to the log area and ensure it's scrolled to the bottom
        log_area.insert(tk.END, message + "\n")
        log_area.see(tk.END)
        logging.info(message)

    def is_valid_url(url):
        # Validate the URL structure
        parsed = urlparse(url)
        return all([parsed.scheme, parsed.netloc])

    try:
        # Load the mod list from the specified JSON file
        with open(json_path, "r") as file:
            mod_list = json.load(file)
        if not isinstance(mod_list, list):
            log_message("Invalid JSON format. Expecting a list of mods.")
            return

        progress_bar["maximum"] = len(mod_list)
        progress_bar["value"] = 0

        for index, mod in enumerate(mod_list):
            if "name" in mod and "url" in mod and is_valid_url(mod["url"]):
                mod_name = mod["name"]
                mod_url, error, metadata = get_download_url_modrinth(mod_name, mod_loader, mc_version)
                if not mod_url:
                    log_message(f"Failed to resolve URL for {mod_name}: {error}")
                    failed_downloads.append({"name": mod_name, "reason": error})
                    progress_bar["value"] = index
                    continue
                save_path = os.path.join(save_directory, f"{mod_name}_{metadata['version_number']}_{mod_loader}.jar")
                try:
                    log_message(f"Downloading {mod_name} (Version: {metadata['version_number']})...")
                    download_mod(mod_url, save_path, metadata)
                    log_message(f"Successfully downloaded {mod_name}.")
                except Exception as e:
                    log_message(f"Failed to download {mod_name}: {e}")
                    failed_downloads.append({"name": mod_name, "reason": str(e)})
                progress_bar["value"] = index + 1  # Increment the progress bar for granular feedback
                progress_bar.update_idletasks()
                time.sleep(1)  # Introduce a short delay to avoid rate-limiting
            else:
                log_message(f"Skipping invalid entry or malformed URL: {mod}")
                failed_downloads.append({"name": mod.get("name", "Unknown"), "reason": "Missing required keys or invalid URL"})
    except Exception as e:
        log_message(f"Error: {e}")

    if failed_downloads:
        # Save failed downloads to a log file
        failed_log = save_failed_downloads(failed_downloads, save_directory)
        log_message(f"Failed downloads logged to {failed_log}")

    elapsed_time = time.time() - start_time
    log_message(f"Download process complete in {elapsed_time:.2f} seconds.")

# File browsing helper function
def browse_file(entry_field):
    filename = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if filename:
        entry_field.delete(0, tk.END)
        entry_field.insert(0, filename)

# Directory browsing helper function
def browse_directory(entry_field):
    directory = filedialog.askdirectory()
    if directory:
        entry_field.delete(0, tk.END)
        entry_field.insert(0, directory)

# Wrapper to run the download process in a separate thread
def start_download_threaded(json_entry, save_entry, mod_loader_box, mc_version_entry, log_area, progress_bar):
    def thread_target():
        try:
            start_download(
                json_entry.get(), save_entry.get(), mod_loader_box.get(),
                mc_version_entry.get(), log_area, progress_bar
            )
        except Exception as e:
            logging.error(f"Error in download thread: {e}")
            log_area.insert(tk.END, f"Thread Error: {e}\n")
            log_area.see(tk.END)
    
    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()

# Helper function to create a label widget
def create_label(root, text, row, column, **kwargs):
    tk.Label(root, text=text).grid(row=row, column=column, **kwargs)

# Helper function to create an entry widget
def create_entry(root, width, row, column, placeholder=None, **kwargs):
    entry = tk.Entry(root, width=width)
    entry.grid(row=row, column=column, **kwargs)
    if placeholder:
        entry.insert(0, placeholder)  # Insert the placeholder text as the default value
    return entry

# Helper function to create a button widget
def create_button(root, text, command, row, column, **kwargs):
    tk.Button(root, text=text, command=command).grid(row=row, column=column, **kwargs)

# Helper function to create a progress bar widget
def create_progress_bar(root, row, column, **kwargs):
    progress_bar = ttk.Progressbar(root, orient="horizontal", mode="determinate", length=400)
    progress_bar.grid(row=row, column=column, **kwargs)
    return progress_bar

# Function to build the GUI for the application
def create_gui():
    root = tk.Tk()
    root.title("Minecraft Mod Downloader")
    root.geometry("700x500")

    create_label(root, "JSON File:", 0, 0, padx=10, pady=5, sticky="e")
    json_entry = create_entry(root, 50, 0, 1, placeholder="Path to mod list JSON", padx=10, pady=5)
    create_button(root, "Browse", lambda: browse_file(json_entry), 0, 2, padx=10, pady=5)

    create_label(root, "Save Directory:", 1, 0, padx=10, pady=5, sticky="e")
    save_entry = create_entry(root, 50, 1, 1, placeholder="Directory to save mods", padx=10, pady=5)
    create_button(root, "Browse", lambda: browse_directory(save_entry), 1, 2, padx=10, pady=5)

    create_label(root, "Mod Loader:", 2, 0, padx=10, pady=5, sticky="e")
    mod_loader_box = Combobox(root, values=["fabric", "forge"])
    mod_loader_box.grid(row=2, column=1, padx=10, pady=5)
    mod_loader_box.set("fabric")

    create_label(root, "Minecraft Version:", 3, 0, padx=10, pady=5, sticky="e")
    mc_version_entry = create_entry(root, 50, 3, 1, placeholder="e.g., 1.21.1", padx=10, pady=5)

    log_area = tk.Text(root, height=15, width=80)
    log_area.grid(row=4, column=0, columnspan=3, padx=10, pady=10)

    progress_bar = create_progress_bar(root, 5, 0, columnspan=3, pady=10)

    create_button(root, "Start", lambda: start_download_threaded(
        json_entry, save_entry, mod_loader_box, mc_version_entry, log_area, progress_bar
    ), 6, 1, pady=10)

    root.mainloop()

if __name__ == "__main__":
    setup_debug_logging()
    create_gui()
